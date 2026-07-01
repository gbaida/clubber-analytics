"""
Aggregation layer: turns the processed ticket DataFrame into chart-ready JSON.

Each function mirrors the inline pandas that lived in the Streamlit tabs of
`dashboard.py`, but returns plain dicts/lists (JSON-serializable) instead of
drawing Plotly figures. The front-end maps these into ECharts options.

Conventions preserved from the original app:
- PT-BR labels.
- COLORS palette, _DOW_MAP day abbreviations.
- "Gratuito" bucket for free tickets (deal_price_brl == 0).
- Reversed-axis charts ("Quando compraram", Comparar "Dias até o Evento").
- Highlight: reference event _HL=#FF7F0E, others _MUTE=#AAAAAA.
"""

from datetime import date, datetime

import pandas as pd

from core import COLORS, _DOW_MAP, _DOW_ORDER

_HL = "#FF7F0E"
_MUTE = "#AAAAAA"


# ── helpers ──────────────────────────────────────────────────────────────────
def _to_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None


def _i(v) -> int:
    return int(v)


def _f(v) -> float:
    return round(float(v), 2)


def build_df(raw_records: list[dict]) -> pd.DataFrame:
    """Processed Shotgun DataFrame (Porta channel deferred to a later version)."""
    from core import process
    df = process(pd.DataFrame(raw_records))
    if not df.empty:
        df["source"] = "Shotgun"
    return df


def apply_filters(df, sel_events, channels, date_from=None, date_to=None):
    """Mirror dashboard.py 990-1001: dff / df_sel / dff_shotgun."""
    if df.empty:
        return df, df, df
    mask = (
        df["event_name"].isin(sel_events)
        & (df["ticket_status"] != "canceled")
        & df["source"].isin(channels)
    )
    df_lo, df_hi = _to_date(date_from), _to_date(date_to)
    if df_lo and df_hi and "order_date" in df.columns:
        mask &= df["order_date"].between(df_lo, df_hi)
    dff = df[mask].copy()
    df_sel = df[df["event_name"].isin(sel_events)].copy()
    dff_shotgun = dff[dff["source"] == "Shotgun"].copy()
    return dff, df_sel, dff_shotgun


# ── summary (filter universe) ────────────────────────────────────────────────
def data_summary(df) -> dict:
    if df.empty:
        return {"events": [], "date_min": None, "date_max": None, "channels": []}
    events = sorted(df["event_name"].dropna().unique().tolist())
    vd = df["order_date"].dropna() if "order_date" in df.columns else pd.Series([], dtype=object)
    dmin = vd.min().isoformat() if not vd.empty else None
    dmax = vd.max().isoformat() if not vd.empty else None
    channels = sorted(df["source"].dropna().unique().tolist())
    return {"events": events, "date_min": dmin, "date_max": dmax, "channels": channels}


# ── KPI header (2×3 grid) ────────────────────────────────────────────────────
def compute_kpis(dff, df_sel, dff_shotgun) -> dict:
    if dff.empty:
        return {k: 0 for k in
                ["ingressos", "participantes", "receita",
                 "comparecimento", "cancelamento", "newsletter"]}
    total_tickets = len(dff)
    unique_attendees = dff["contact_id"].nunique() if "contact_id" in dff else 0
    total_revenue = dff["deal_price_brl"].sum() if "deal_price_brl" in dff else 0

    df_sel_sg = df_sel[df_sel["source"] == "Shotgun"]
    total_canceled = (df_sel_sg["ticket_status"] == "canceled").sum()
    cancel_rate = total_canceled / len(df_sel_sg) * 100 if len(df_sel_sg) else 0
    sg_total = len(dff_shotgun)
    scanned = dff_shotgun["ticket_scanned_at"].notna().sum() if "ticket_scanned_at" in dff_shotgun else 0
    scan_rate = scanned / sg_total * 100 if sg_total else 0
    nl = dff_shotgun["contact_newsletter_optin"] if "contact_newsletter_optin" in dff_shotgun else pd.Series([], dtype=object)
    newsletter_rate = (nl.sum() / nl.notna().sum() * 100) if nl.notna().sum() > 0 else 0

    return {
        "ingressos":      _i(total_tickets),
        "participantes":  _i(unique_attendees),
        "receita":        _f(total_revenue),
        "comparecimento": round(float(scan_rate), 1),
        "cancelamento":   round(float(cancel_rate), 1),
        "newsletter":     round(float(newsletter_rate), 1),
    }


# ══════════════════════════════════════════════════════════════════════════════
# VENDAS
# ══════════════════════════════════════════════════════════════════════════════
def vendas_payload(dff, df_sel, sel_events) -> dict:
    out: dict = {}
    multi = len(sel_events) > 1

    # 1 & 2 — Vendas diárias + acumuladas
    if "order_date" in dff.columns and not dff.empty:
        daily = (
            dff.groupby(["order_date", "event_name"]).size().reset_index(name="ingressos")
        )
        daily["order_date"] = pd.to_datetime(daily["order_date"])
        daily = daily.sort_values("order_date")
        if multi:
            # Multi-event: align by "Dias até o Evento" (days until the event),
            # reversed so event day (0) sits on the right — same as the Comparar tab.
            use_until = "event_start_time" in dff.columns and dff["event_start_time"].notna().any()
            if use_until:
                ev_start = (
                    dff.groupby("event_name")["event_start_time"].min()
                    .dt.tz_convert(None).dt.normalize().rename("event_start")
                )
                daily = daily.merge(ev_start, on="event_name")
                daily["x"] = (daily["event_start"] - daily["order_date"]).dt.days
                x_label = "Dias até o Evento"
            else:
                first_sale = daily.groupby("event_name")["order_date"].min().rename("first_sale")
                daily = daily.merge(first_sale, on="event_name")
                daily["x"] = (daily["order_date"] - daily["first_sale"]).dt.days
                x_label = "Dias desde a 1ª Venda"
            x_reversed = bool(use_until)
        else:
            daily["x"] = daily["order_date"].dt.strftime("%Y-%m-%d")
            x_label = "Data"
            x_reversed = False
        # cumsum must accumulate chronologically regardless of the x metric
        daily = daily.sort_values("order_date")
        daily["acumulado"] = daily.groupby("event_name")["ingressos"].cumsum()

        series_d, series_c = [], []
        for ev in sorted(daily["event_name"].unique().tolist()):
            sub = daily[daily["event_name"] == ev]
            series_d.append({"name": ev,
                             "data": [[(_i(x) if multi else x), _i(y)]
                                      for x, y in zip(sub["x"], sub["ingressos"])]})
            series_c.append({"name": ev,
                             "data": [[(_i(x) if multi else x), _i(y)]
                                      for x, y in zip(sub["x"], sub["acumulado"])]})
        out["diarias"]   = {"multi": multi, "x_label": x_label, "reversed": x_reversed, "series": series_d}
        out["acumulado"] = {"multi": multi, "x_label": x_label, "reversed": x_reversed, "series": series_c}

    # 3 — Vendas por dia da semana
    if "order_dow" in dff.columns and not dff.empty:
        dow = dff.groupby("order_dow").size()
        out["dia_semana"] = {
            "categories": [_DOW_MAP[d] for d in _DOW_ORDER],
            "data": [_i(dow.get(d, 0)) for d in _DOW_ORDER],
        }

    # 4 — Quando compraram (x reversed)
    if "days_before_event" in dff.columns and not dff.empty:
        pre = dff[dff["days_before_event"] >= 0].copy()
        pre["bucket"] = pre["days_before_event"].clip(upper=30).astype(int)
        counts = pre.groupby("bucket").size()
        out["quando_compraram"] = {
            "x_label": "Dias Antes do Evento", "reversed": True,
            "data": [[_i(b), _i(c)] for b, c in counts.items()],
        }

    # 5 — Heatmap dia × hora
    if "order_hour" in dff.columns and "order_dow" in dff.columns and not dff.empty:
        heat = dff.groupby(["order_dow", "order_hour"]).size().reset_index(name="ingressos")
        present = [d for d in _DOW_ORDER if d in heat["order_dow"].values]
        data = []
        for _, r in heat.iterrows():
            di = present.index(r["order_dow"])
            data.append([_i(r["order_hour"]), di, _i(r["ingressos"])])
        out["heatmap"] = {
            "dows": [_DOW_MAP[d] for d in present],
            "hours": list(range(24)),
            "data": data,
        }

    # 6 — Resumo por evento (table)
    out["resumo"] = _resumo_por_evento(df_sel)
    return out


def _resumo_por_evento(df_sel) -> list[dict]:
    if df_sel.empty:
        return []
    _od_min = (
        df_sel[df_sel["order_date"].notna()].groupby("event_name")["order_date"]
        .min().rename("primeira_venda")
    )
    if "event_start_time" in df_sel.columns:
        _est_min = df_sel.groupby("event_name")["event_start_time"].min().rename("data_evento")
        event_dates = _est_min.to_frame().join(_od_min, how="left").reset_index()
        event_dates["dias_de_vendas"] = (
            event_dates["data_evento"].dt.tz_convert(None).dt.normalize()
            - pd.to_datetime(event_dates["primeira_venda"])
        ).dt.days
    else:
        event_dates = _od_min.to_frame().reset_index()
        event_dates["dias_de_vendas"] = None

    summary = df_sel.groupby("event_name").agg(
        total=("ticket_id", "count"),
        validos=("ticket_status", lambda x: int((x == "valid").sum())),
        cancelados=("ticket_status", lambda x: int((x == "canceled").sum())),
        lidos=("ticket_scanned_at", "count"),
        receita=("deal_price_brl", "sum"),
    ).reset_index()
    summary = summary.merge(event_dates[["event_name", "dias_de_vendas"]], on="event_name", how="left")

    rows = []
    for _, r in summary.iterrows():
        validos = int(r["validos"]) or 1
        total = int(r["total"]) or 1
        rows.append({
            "Evento": r["event_name"],
            "Total": _i(r["total"]),
            "Válidos": _i(r["validos"]),
            "Cancelados": _i(r["cancelados"]),
            "Comparecimento": _i(r["lidos"]),
            "Receita": _f(r["receita"]),
            "Dias de Venda": (None if pd.isna(r["dias_de_vendas"]) else _i(r["dias_de_vendas"])),
            "Taxa de Comparecimento": round(int(r["lidos"]) / validos * 100, 1),
            "Taxa de Cancelamento": round(int(r["cancelados"]) / total * 100, 1),
        })
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# COMPARAR  (needs >= 2 events)
# ══════════════════════════════════════════════════════════════════════════════
def comparar_payload(dff, sel_events, ref_event) -> dict:
    if len(sel_events) < 2 or dff.empty:
        return {"ok": False}
    if ref_event not in sel_events:
        ref_event = sorted(sel_events)[0]

    dff_ref = dff[dff["event_name"] == ref_event]
    other_evs = [e for e in sel_events if e != ref_event]

    def _kpis(d):
        total = len(d)
        receita = d["deal_price_brl"].sum() if "deal_price_brl" in d.columns else 0
        pago = (d["deal_price_brl"] > 0).mean() * 100 if "deal_price_brl" in d.columns else 0
        scan = d["ticket_scanned_at"].notna().mean() * 100 if "ticket_scanned_at" in d.columns else 0
        return total, receita, pago, scan

    ref_k = _kpis(dff_ref)
    avg_k = tuple(
        sum(_kpis(dff[dff["event_name"] == e])[i] for e in other_evs) / len(other_evs)
        for i in range(4)
    )

    out: dict = {
        "ok": True,
        "ref_event": ref_event,
        "kpis": {
            "ingressos":      {"ref": _i(ref_k[0]), "delta": _i(round(ref_k[0] - avg_k[0]))},
            "receita":        {"ref": _f(ref_k[1]), "delta": _f(ref_k[1] - avg_k[1])},
            "pagos":          {"ref": round(float(ref_k[2]), 1), "delta": round(float(ref_k[2] - avg_k[2]), 1)},
            "comparecimento": {"ref": round(float(ref_k[3]), 1), "delta": round(float(ref_k[3] - avg_k[3]), 1)},
        },
        "colors": {"hl": _HL, "mute": _MUTE},
    }

    # Receita / Ingressos por evento (highlight ref)
    ev_sum = dff.groupby("event_name").agg(
        receita=("deal_price_brl", "sum"),
        ingressos=("ticket_id", "count"),
    ).reset_index()
    rev_sorted = ev_sum.sort_values("receita", ascending=False)
    tix_sorted = ev_sum.sort_values("ingressos", ascending=False)
    out["receita_evento"] = {
        "events": rev_sorted["event_name"].tolist(),
        "values": [_f(v) for v in rev_sorted["receita"]],
        "ref": ref_event,
    }
    out["ingressos_evento"] = {
        "events": tix_sorted["event_name"].tolist(),
        "values": [_i(v) for v in tix_sorted["ingressos"]],
        "ref": ref_event,
    }

    # Primeira Vez vs Recorrente
    contacts_by_ev = dff.groupby("event_name")["contact_id"].apply(set)
    loyalty = []
    for ev in sel_events:
        ev_c = contacts_by_ev.get(ev, set())
        other_c = set().union(*[contacts_by_ev.get(e, set()) for e in sel_events if e != ev]) if other_evs else set()
        loyalty.append({"event": ev,
                        "primeira_vez": _i(len(ev_c - other_c)),
                        "recorrente": _i(len(ev_c & other_c))})
    ev_ord = tix_sorted["event_name"].tolist()
    out["fidelidade"] = {"order": ev_ord, "ref": ref_event,
                         "rows": sorted(loyalty, key=lambda r: ev_ord.index(r["event"]))}

    # Pago vs Gratuito
    if "deal_price_brl" in dff.columns:
        tmp = dff.copy()
        tmp["_ctype"] = tmp["deal_price_brl"].apply(lambda x: "Gratuito" if x == 0 else "Pago")
        grp = tmp.groupby(["event_name", "_ctype"]).size().unstack(fill_value=0)
        rows = []
        for ev in ev_ord:
            pago = int(grp.loc[ev, "Pago"]) if ev in grp.index and "Pago" in grp.columns else 0
            grat = int(grp.loc[ev, "Gratuito"]) if ev in grp.index and "Gratuito" in grp.columns else 0
            rows.append({"event": ev, "pago": pago, "gratuito": grat})
        out["pago_gratuito"] = {"order": ev_ord, "ref": ref_event, "rows": rows}

    # 4 evolution charts — "Dias até o Evento" (reversed); fallback to 1ª venda
    if "order_date" in dff.columns:
        out["evolucao"] = _comparar_evolution(dff, ref_event, other_evs)
    return out


def _comparar_evolution(dff, ref_event, other_evs) -> dict:
    use_until = "event_start_time" in dff.columns and dff["event_start_time"].notna().any()
    x_label = "Dias até o Evento" if use_until else "Dias desde a 1ª Venda"

    # tickets
    daily = dff.groupby(["order_date", "event_name"]).size().reset_index(name="ingressos")
    daily["order_date"] = pd.to_datetime(daily["order_date"])
    daily = _add_dia(daily, dff, use_until)
    daily["acumulado"] = daily.groupby("event_name")["ingressos"].cumsum()

    # revenue
    drev = dff.groupby(["order_date", "event_name"])["deal_price_brl"].sum().reset_index(name="receita")
    drev["order_date"] = pd.to_datetime(drev["order_date"])
    drev = _add_dia(drev, dff, use_until)
    drev["receita_acum"] = drev.groupby("event_name")["receita"].cumsum()

    def pack(frame, ycol, integer):
        ref = frame[frame["event_name"] == ref_event].sort_values("dia")
        cast = _i if integer else _f
        ref_pts = [[_i(d), cast(y)] for d, y in zip(ref["dia"], ref[ycol])]
        others = []
        for ev in other_evs:
            sub = frame[frame["event_name"] == ev].sort_values("dia")
            others.append({"name": ev, "data": [[_i(d), cast(y)] for d, y in zip(sub["dia"], sub[ycol])]})
        avg = (
            frame[frame["event_name"] != ref_event].groupby("dia")[ycol].mean().reset_index()
        )
        avg_pts = [[_i(d), cast(y)] for d, y in zip(avg["dia"], avg[ycol])]
        return {"ref": {"name": ref_event, "data": ref_pts}, "others": others, "avg": avg_pts}

    return {
        "x_label": x_label, "reversed": bool(use_until),
        "vendas_diaria":   pack(daily, "ingressos", True),
        "vendas_acum":     pack(daily, "acumulado", True),
        "receita_diaria":  pack(drev, "receita", False),
        "receita_acum":    pack(drev, "receita_acum", False),
    }


def _add_dia(frame, dff, use_until):
    if use_until:
        ev_start = (
            dff.groupby("event_name")["event_start_time"].min()
            .dt.tz_convert(None).dt.normalize().rename("event_start")
        )
        frame = frame.merge(ev_start, on="event_name")
        frame["dia"] = (frame["event_start"] - frame["order_date"]).dt.days
    else:
        fs = frame.groupby("event_name")["order_date"].min().rename("first_sale")
        frame = frame.merge(fs, on="event_name")
        frame["dia"] = (frame["order_date"] - frame["first_sale"]).dt.days
    return frame


# ══════════════════════════════════════════════════════════════════════════════
# RECEITA  (dashboard.py 1226-1324)
# ══════════════════════════════════════════════════════════════════════════════
def receita_payload(dff, sel_events) -> dict:
    out: dict = {}
    if dff.empty or "deal_price_brl" not in dff.columns:
        return out
    multi = len(sel_events) > 1

    # 1 — Receita por Evento (multi só)
    if multi:
        ev = dff.groupby("event_name")["deal_price_brl"].sum().sort_values(ascending=False)
        out["receita_evento"] = {
            "categories": ev.index.tolist(),
            "values": [_f(v) for v in ev.values],
        }

    # 2 — Receita por Categoria de Ingresso
    cat = dff["deal_title"].where(dff["deal_price_brl"] > 0, "Gratuito")
    rev_tier = dff.assign(_cat=cat).groupby("_cat")["deal_price_brl"].sum().sort_values(ascending=False)
    out["receita_categoria"] = {
        "categories": rev_tier.index.tolist(),
        "values": [_f(v) for v in rev_tier.values],
    }

    # 3 — Tipos de Ingresso Gratuito
    free = dff[dff["deal_price_brl"] == 0]
    if not free.empty:
        fc = free.groupby("deal_title").size().sort_values(ascending=False)
        out["ingressos_gratuitos"] = {
            "categories": fc.index.tolist(),
            "values": [_i(v) for v in fc.values],
        }

    # 4 — Receita por Método de Pagamento
    if "payment_method" in dff.columns:
        paid = dff[dff["deal_price_brl"] > 0].copy()
        paid["payment_method"] = paid["payment_method"].replace({"": "outro"}).fillna("outro")
        pay = paid.groupby("payment_method")["deal_price_brl"].sum().sort_values(ascending=False)
        out["receita_pagamento"] = {
            "categories": pay.index.tolist(),
            "values": [_f(v) for v in pay.values],
        }

    # 5 — Ingressos Gratuitos vs Pagos (donut)
    tipo = dff["deal_price_brl"].apply(lambda x: "Gratuito" if x == 0 else "Pago").value_counts()
    out["gratuito_pago"] = {
        "labels": tipo.index.tolist(),
        "values": [_i(v) for v in tipo.values],
    }

    # 6 — Receita Diária ao Longo do Tempo (single-event só)
    if "order_date" in dff.columns and not multi:
        rd = dff[dff["order_date"].notna()].groupby("order_date")["deal_price_brl"].sum().reset_index()
        rd["order_date"] = pd.to_datetime(rd["order_date"])
        rd = rd.sort_values("order_date")
        out["receita_diaria"] = {
            "dates": [d.strftime("%Y-%m-%d") for d in rd["order_date"]],
            "values": [_f(v) for v in rd["deal_price_brl"]],
        }
    return out


# ══════════════════════════════════════════════════════════════════════════════
# MARKETING  (dashboard.py 1329-1376) — Shotgun rows only
# ══════════════════════════════════════════════════════════════════════════════
def marketing_payload(dff, sel_events) -> dict:
    out: dict = {}
    if dff.empty:
        return out
    multi = len(sel_events) > 1

    # 1 — Ingressos por Canal de Aquisição (barra horizontal, menor→maior)
    if "utm_source" in dff.columns:
        src = dff["utm_source"].value_counts().sort_values(ascending=True)
        out["canal_aquisicao"] = {
            "categories": src.index.tolist(),
            "values": [_i(v) for v in src.values],
        }

    # 2 — Canal × Meio (App vs Web) (empilhado)
    if "utm_source" in dff.columns and "utm_medium" in dff.columns:
        grp = dff.groupby(["utm_source", "utm_medium"]).size().unstack(fill_value=0)
        order = grp.sum(axis=1).sort_values(ascending=False).index.tolist()
        grp = grp.loc[order]
        out["canal_meio"] = {
            "categories": order,
            "series": [{"name": str(m), "data": [_i(v) for v in grp[m].values]}
                       for m in grp.columns],
        }

    # 3 — Performance por Canal e Evento (agrupado, multi só)
    if multi and "utm_source" in dff.columns:
        grp = dff.groupby(["event_name", "utm_source"]).size().unstack(fill_value=0)
        out["canal_evento"] = {
            "categories": grp.index.tolist(),
            "series": [{"name": str(s), "data": [_i(v) for v in grp[s].values]}
                       for s in grp.columns],
        }
    return out


# ══════════════════════════════════════════════════════════════════════════════
# PÚBLICO  (dashboard.py 1381-1507) — Shotgun rows only, unique por contato
# ══════════════════════════════════════════════════════════════════════════════
def audience_payload(dff, sel_events) -> dict:
    out: dict = {}
    if dff.empty:
        return out
    multi = len(sel_events) > 1
    uniq = dff.drop_duplicates("contact_id") if "contact_id" in dff.columns else dff
    _age_range = list(range(16, 81))

    # 1 — Gênero do Público (donut)
    if "contact_gender" in dff.columns:
        g = uniq["contact_gender"].replace({"-": None, "": None}).dropna().value_counts()
        out["genero"] = {"labels": g.index.tolist(), "values": [_i(v) for v in g.values]}

    # 2 — Distribuição de Idade
    if "age" in dff.columns:
        ages = uniq["age"].dropna()
        ages = ages[(ages >= 16) & (ages <= 80)].astype(int)
        vc = ages.value_counts()
        out["idade"] = {
            "ages": [str(a) for a in _age_range],
            "values": [_i(vc.get(a, 0)) for a in _age_range],
        }

    # 3 — Top 15 Cidades (barra horizontal)
    if "contact_locality" in dff.columns:
        cities = (
            uniq["contact_locality"].replace({"-": None, "01008-000": None, "": None})
            .dropna().value_counts().head(15).sort_values(ascending=True)
        )
        out["cidades"] = {
            "categories": cities.index.tolist(),
            "values": [_i(v) for v in cities.values],
        }

    # 4 — Taxa de Opt-in Newsletter (donut)
    if "contact_newsletter_optin" in dff.columns:
        opt = (
            uniq["contact_newsletter_optin"].map({True: "Inscrito", False: "Não Inscrito"})
            .dropna().value_counts()
        )
        out["newsletter"] = {"labels": opt.index.tolist(), "values": [_i(v) for v in opt.values]}

    # 5 — Participantes Recorrentes (multi só)
    if multi and "event_id" in dff.columns:
        epc = dff.groupby("contact_id")["event_id"].nunique()
        loy = epc.value_counts().sort_index()
        out["recorrentes"] = {
            "categories": [f"{int(n)} evento{'s' if n > 1 else ''}" for n in loy.index],
            "values": [_i(v) for v in loy.values],
        }

    # 6 — Top 10 Participantes Mais Fiéis (multi só, barra horizontal)
    if multi and "event_id" in dff.columns:
        name_col = next((c for c in ["contact_name", "contact_email"] if c in dff.columns), None)
        top = (
            dff.groupby("contact_id")["event_id"].nunique()
            .reset_index(name="eventos").sort_values("eventos", ascending=False).head(10)
        )
        if name_col:
            top = top.merge(
                dff[["contact_id", name_col]].drop_duplicates("contact_id"),
                on="contact_id", how="left",
            )
            labels = top[name_col].fillna(top["contact_id"].astype(str)).tolist()
        else:
            labels = top["contact_id"].astype(str).tolist()
        pairs = list(zip(labels, [_i(v) for v in top["eventos"]]))[::-1]  # menor→maior p/ horizontal
        out["top_fieis"] = {
            "categories": [str(p[0]) for p in pairs],
            "values": [p[1] for p in pairs],
        }

    # 7 — Distribuição de Idade por Gênero (overlay)
    if "age" in dff.columns and "contact_gender" in dff.columns:
        ag = uniq[["age", "contact_gender"]].replace({"-": None, "": None}).dropna()
        ag = ag[(ag["age"] >= 16) & (ag["age"] <= 80)]
        ag = ag.assign(age=ag["age"].astype(int))
        series = []
        for gen in ag["contact_gender"].unique().tolist():
            vc = ag[ag["contact_gender"] == gen]["age"].value_counts()
            series.append({"name": str(gen), "data": [_i(vc.get(a, 0)) for a in _age_range]})
        out["idade_genero"] = {"ages": [str(a) for a in _age_range], "series": series}
    return out


# ══════════════════════════════════════════════════════════════════════════════
# OPERAÇÕES  (dashboard.py 1512-1624) — Shotgun rows only
# ══════════════════════════════════════════════════════════════════════════════
_SCAN_COLORS = {
    ("Pago", "Presente"): "#00CC96",
    ("Pago", "Ausente"): "#EF553B",
    ("Gratuito", "Presente"): "#72EFDD",
    ("Gratuito", "Ausente"): "#FF9F7F",
}


def operacoes_payload(dff, df_sel, sel_events) -> dict:
    out: dict = {}
    if dff.empty:
        return out

    # 1 — Comparecimento por Evento (empilhado Pago/Gratuito × Presente/Ausente)
    tt = (
        dff["deal_price_brl"].apply(lambda x: "Gratuito" if x == 0 else "Pago")
        if "deal_price_brl" in dff.columns
        else pd.Series("Pago", index=dff.index)
    )
    scan = dff.assign(_tt=tt).groupby(["event_name", "_tt"]).agg(
        total=("ticket_id", "count"),
        presentes=("ticket_scanned_at", "count"),
    ).reset_index()
    scan["ausentes"] = scan["total"] - scan["presentes"]
    events_order = (
        scan.groupby("event_name")["total"].sum().sort_values(ascending=False).index.tolist()
    )
    series = []
    for ttype in ["Pago", "Gratuito"]:
        sub = scan[scan["_tt"] == ttype]
        if sub.empty:
            continue
        m = sub.set_index("event_name")
        for status, col in [("Presente", "presentes"), ("Ausente", "ausentes")]:
            series.append({
                "name": f"{ttype} – {status}", "stack": ttype,
                "color": _SCAN_COLORS[(ttype, status)],
                "data": [_i(m[col].get(ev, 0)) for ev in events_order],
            })
    out["comparecimento"] = {"categories": events_order, "series": series}

    # 2 & 3 — Cancelamento + Status (df_sel: inclui cancelados)
    if not df_sel.empty:
        ce = df_sel.groupby("event_name").agg(
            total=("ticket_id", "count"),
            cancelados=("ticket_status", lambda x: int((x == "canceled").sum())),
        )
        ce["taxa"] = ce["cancelados"] / ce["total"] * 100
        out["cancelamento"] = {
            "categories": ce.index.tolist(),
            "values": [round(float(v), 1) for v in ce["taxa"].values],
        }
        sc = df_sel["ticket_status"].value_counts()
        out["status"] = {"categories": sc.index.tolist(), "values": [_i(v) for v in sc.values]}

    # 4 — Mix de Categorias por Evento (empilhado)
    cat = (
        dff["deal_title"].where(dff["deal_price_brl"] > 0, "Gratuito")
        if "deal_price_brl" in dff.columns
        else dff["deal_title"]
    )
    mix = dff.assign(_cat=cat).groupby(["event_name", "_cat"]).size().unstack(fill_value=0)
    out["mix_categoria"] = {
        "categories": mix.index.tolist(),
        "series": [{"name": str(c), "data": [_i(v) for v in mix[c].values]} for c in mix.columns],
    }
    return out
