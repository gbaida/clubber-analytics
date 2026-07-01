"""
Clubber Analytics v2 — pure data layer.

Extracted verbatim (minus Streamlit) from the original single-file Streamlit app
(`dashboard.py`). No `st.*` here — everything is a plain function over pandas.
"""

import json
import math as _math
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import requests

# ── Shared constants (mirror dashboard.py) ─────────────────────────────────────
# Plotly qualitative palette, hard-coded so the backend needn't import plotly.
COLORS = [
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52",
]

_DOW_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_DOW_MAP = dict(zip(_DOW_ORDER, ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]))

# ── Shotgun API fetch ──────────────────────────────────────────────────────────
_TICKETS_URL = "https://api.shotgun.live/tickets"
_TIMEOUT = 60
_MAX_RETRIES = 3


def _api_get(url: str, params: dict, token: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.Timeout:
            if attempt == _MAX_RETRIES:
                raise requests.Timeout(
                    f"A API do Shotgun não respondeu após {_MAX_RETRIES} tentativas "
                    f"({_TIMEOUT}s cada). Tente novamente em alguns instantes."
                )
        except requests.HTTPError:
            raise


def _parse_after(next_url: str) -> str | None:
    values = parse_qs(urlparse(next_url).query).get("after", [])
    return values[0] if values else None


def fetch_tickets_from_api(token: str, organizer_id: str) -> pd.DataFrame:
    params: dict = {"organizer_id": organizer_id}
    all_records: list[dict] = []
    cursor: str | None = None

    while True:
        if cursor:
            params["after"] = cursor
        data = _api_get(_TICKETS_URL, params, token)
        records = data.get("data", [])
        next_url = data.get("pagination", {}).get("next")
        all_records.extend(records)
        if not records or not next_url:
            break
        cursor = _parse_after(next_url)

    return pd.DataFrame(all_records)


# ── JSON serialization helper (used when persisting to Supabase) ───────────────
def _sanitize_for_json(v):
    """Convert non-JSON-serializable pandas/numpy scalars to Python-native types."""
    if v is None:
        return None
    try:
        if pd.isnull(v):          # catches NaT, NaN, None
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, float) and (_math.isnan(v) or _math.isinf(v)):
        return None
    if hasattr(v, "isoformat"):   # Timestamp / datetime / date → ISO string
        return v.isoformat()
    if hasattr(v, "item"):        # numpy int64 / float64 → Python native
        return v.item()
    return v


def _sanitize_record(record: dict) -> dict:
    return {k: _sanitize_for_json(val) for k, val in record.items()}


# ── Data processing ────────────────────────────────────────────────────────────
def process(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["ordered_at", "event_start_time", "event_end_time",
                "ticket_scanned_at", "ticket_canceled_at", "event_published_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    if "contact_birthday" in df.columns:
        df["contact_birthday"] = pd.to_datetime(df["contact_birthday"], errors="coerce", utc=False)
        now = pd.Timestamp.now()
        df["age"] = (
            (now - df["contact_birthday"].dt.tz_localize(None)).dt.days / 365.25
        ).round(0).astype("Int64")

    for col in ["deal_price", "deal_user_service_fee", "deal_producer_cost"]:
        if col in df.columns:
            df[f"{col}_brl"] = pd.to_numeric(df[col], errors="coerce") / 100

    if "utm_source" in df.columns:
        df["utm_source"] = (
            df["utm_source"].fillna("direto").str.lower().str.strip()
            .str.replace(r"\.com$", "", regex=True)
            .replace({"": "direto", "direct": "direto"})
        )
    if "utm_medium" in df.columns:
        df["utm_medium"] = df["utm_medium"].fillna("desconhecido")

    if "contact_newsletter_optin" in df.columns:
        df["contact_newsletter_optin"] = df["contact_newsletter_optin"].map(
            {"True": True, "False": False, True: True, False: False}
        )

    if "ordered_at" in df.columns and "event_start_time" in df.columns:
        df["days_before_event"] = (
            df["event_start_time"] - df["ordered_at"]
        ).dt.total_seconds() / 86400

    if "ordered_at" in df.columns:
        # Use .apply so missing rows become None (not NaT).
        # NaT in an object-dtype column breaks groupby min/max in pandas 2.x.
        df["order_date"] = df["ordered_at"].apply(
            lambda ts: ts.date() if pd.notna(ts) else None
        )
        df["order_hour"] = df["ordered_at"].dt.hour
        df["order_dow"]  = df["ordered_at"].dt.day_name()

    return df


def load_csv(source) -> pd.DataFrame:
    return process(pd.read_csv(source))


# ── Porta (vendas externas: dinheiro / PagBank) ───────────────────────────────
def _read_pagbank(file) -> pd.DataFrame:
    file.seek(0)
    raw = pd.read_csv(file, skiprows=8)
    raw.columns = [c.strip() for c in raw.columns]
    raw = raw[raw["Tipo"].astype(str).str.strip() == "Vendas"].copy()
    raw["Entradas"] = pd.to_numeric(raw["Entradas"], errors="coerce")
    raw = raw[raw["Entradas"].notna() & (raw["Entradas"] > 0)]
    raw["Data"] = pd.to_datetime(raw["Data"], format="%d/%m/%Y", errors="coerce").dt.date
    raw = raw[raw["Data"].notna()]
    return raw


def parse_pagbank_csv(file) -> tuple[int, float, list[float]]:
    sales = _read_pagbank(file)
    prices = sales["Entradas"].astype(float).tolist()
    return len(prices), float(sum(prices)), prices


def parse_pagbank_csv_by_date(file) -> dict:
    sales = _read_pagbank(file)
    out: dict = {}
    for d, group in sales.groupby("Data"):
        prices = group["Entradas"].astype(float).tolist()
        out[d] = (len(prices), float(sum(prices)), prices)
    return out


def porta_totals_by_event(entries: list[dict]) -> pd.DataFrame:
    if not entries:
        return pd.DataFrame(columns=["event_name", "porta_tickets", "porta_revenue"])
    df = pd.DataFrame(entries)
    return (
        df.groupby("event_name", as_index=False)
        .agg(porta_tickets=("tickets", "sum"), porta_revenue=("revenue_brl", "sum"))
    )


def expand_porta_to_rows(entries: list[dict], shotgun_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Expand Porta aggregate entries into one row per ticket, matching shotgun_df schema."""
    if not entries:
        return pd.DataFrame()

    event_dates: dict = {}
    if shotgun_df is not None and "event_name" in shotgun_df and "event_start_time" in shotgun_df:
        for ev, grp in shotgun_df.groupby("event_name"):
            d = grp["event_start_time"].dropna()
            if not d.empty:
                event_dates[ev] = d.min().date()

    rows: list[dict] = []
    for entry in entries:
        evt    = entry["event_name"]
        n      = int(entry.get("tickets", 0))
        rev    = float(entry.get("revenue_brl", 0.0))
        prices = entry.get("prices")
        if entry.get("date"):
            try:
                order_d = datetime.fromisoformat(entry["date"]).date()
            except Exception:
                order_d = None
        else:
            order_d = None
        if order_d is None:
            order_d = event_dates.get(evt) or datetime.now().date()

        if prices and len(prices) == n:
            ticket_prices = [float(p) for p in prices]
        else:
            avg = (rev / n) if n else 0.0
            ticket_prices = [avg] * n

        for p in ticket_prices:
            rows.append({
                "event_name":     evt,
                "deal_price_brl": p,
                "ticket_status":  "valid",
                "source":         "Porta",
                "order_date":     order_d,
            })

    return pd.DataFrame(rows)
