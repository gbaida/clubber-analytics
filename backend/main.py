"""
Clubber Analytics v2 — FastAPI backend.

Serves the static front-end (frontend/) and a small JSON API. Auth is handled
client-side with supabase-js; every /api route (except /api/config) expects an
`Authorization: Bearer <jwt>` header, which is validated against Supabase and
used for RLS-scoped queries.

Run:  uvicorn main:app --reload --port 8000   (from the backend/ dir)
"""

from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import charts
import core
import supa

app = FastAPI(title="Clubber Analytics API")

_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


# ── auth dependency ──────────────────────────────────────────────────────────
def current_user(authorization: str = Header(default="")):
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    jwt = authorization.split(" ", 1)[1].strip()
    user = supa.get_user(jwt)
    if user is None:
        raise HTTPException(401, "Invalid or expired token")
    return {"id": user.id, "email": user.email, "jwt": jwt}


def _load_df(user) -> pd.DataFrame:
    """Load the user's tickets from Supabase, processed and tagged Shotgun."""
    client = supa.client_for(user["jwt"])
    raw = supa.load_all_raw(client, user["id"])
    return charts.build_df(raw)


# ── config (public) ──────────────────────────────────────────────────────────
@app.get("/api/config")
def config():
    """Public Supabase creds the front-end needs to init supabase-js."""
    return {"supabase_url": supa.SUPABASE_URL, "supabase_anon_key": supa.SUPABASE_ANON_KEY}


# ── auth check ───────────────────────────────────────────────────────────────
@app.get("/api/me")
def me(user=Depends(current_user)):
    return {"id": user["id"], "email": user["email"]}


# ── data fetch / clear ───────────────────────────────────────────────────────
class FetchBody(BaseModel):
    organizer_id: str
    token: str


@app.post("/api/tickets/fetch")
def fetch(body: FetchBody, user=Depends(current_user)):
    raw_df = core.fetch_tickets_from_api(body.token, body.organizer_id)
    if raw_df.empty:
        return {"n_new": 0, "n_existing": 0}

    client = supa.client_for(user["jwt"])
    existing = supa.load_existing_ticket_ids(client, user["id"])
    all_recs = raw_df.to_dict("records")
    new_recs = [r for i, r in enumerate(all_recs)
                if str(r.get("ticket_id", i)) not in existing]

    rows = [
        {"user_id": user["id"],
         "ticket_id": str(r.get("ticket_id", i)),
         "raw": core._sanitize_record(r)}
        for i, r in enumerate(new_recs)
    ]
    supa.upsert_tickets(client, rows)
    return {"n_new": len(new_recs), "n_existing": len(existing)}


@app.delete("/api/tickets")
def clear(user=Depends(current_user)):
    client = supa.client_for(user["jwt"])
    supa.delete_tickets(client, user["id"])
    return {"ok": True}


# ── summary + kpis ───────────────────────────────────────────────────────────
@app.get("/api/data/summary")
def summary(user=Depends(current_user)):
    df = _load_df(user)
    return {"loaded": not df.empty, **charts.data_summary(df)}


def _parse_filters(events: str, channels: str):
    sel_events = [e for e in events.split("|") if e] if events else []
    sel_channels = [c for c in channels.split("|") if c] if channels else ["Shotgun"]
    return sel_events, sel_channels


@app.get("/api/kpis")
def kpis(user=Depends(current_user), events: str = "", channels: str = "Shotgun",
         date_from: str = "", date_to: str = ""):
    df = _load_df(user)
    if df.empty:
        raise HTTPException(404, "Nenhum dado carregado")
    sel_events, sel_channels = _parse_filters(events, channels)
    if not sel_events:
        sel_events = charts.data_summary(df)["events"]
    dff, df_sel, dff_sg = charts.apply_filters(df, sel_events, sel_channels, date_from, date_to)
    return charts.compute_kpis(dff, df_sel, dff_sg)


# ── chart endpoints ──────────────────────────────────────────────────────────
@app.get("/api/charts/vendas")
def vendas(user=Depends(current_user), events: str = "", channels: str = "Shotgun",
           date_from: str = "", date_to: str = ""):
    df = _load_df(user)
    if df.empty:
        raise HTTPException(404, "Nenhum dado carregado")
    sel_events, sel_channels = _parse_filters(events, channels)
    if not sel_events:
        sel_events = charts.data_summary(df)["events"]
    dff, df_sel, _ = charts.apply_filters(df, sel_events, sel_channels, date_from, date_to)
    return charts.vendas_payload(dff, df_sel, sel_events)


@app.get("/api/charts/comparar")
def comparar(user=Depends(current_user), events: str = "", channels: str = "Shotgun",
             ref_event: str = "", date_from: str = "", date_to: str = ""):
    df = _load_df(user)
    if df.empty:
        raise HTTPException(404, "Nenhum dado carregado")
    sel_events, sel_channels = _parse_filters(events, channels)
    if not sel_events:
        sel_events = charts.data_summary(df)["events"]
    dff, _, _ = charts.apply_filters(df, sel_events, sel_channels, date_from, date_to)
    return charts.comparar_payload(dff, sel_events, ref_event)


def _filtered(user, events, channels, date_from, date_to):
    """Shared prelude for the tab endpoints: load, resolve events, apply filters."""
    df = _load_df(user)
    if df.empty:
        raise HTTPException(404, "Nenhum dado carregado")
    sel_events, sel_channels = _parse_filters(events, channels)
    if not sel_events:
        sel_events = charts.data_summary(df)["events"]
    dff, df_sel, dff_sg = charts.apply_filters(df, sel_events, sel_channels, date_from, date_to)
    return dff, df_sel, dff_sg, sel_events


@app.get("/api/charts/receita")
def receita(user=Depends(current_user), events: str = "", channels: str = "Shotgun",
            date_from: str = "", date_to: str = ""):
    dff, _, _, sel_events = _filtered(user, events, channels, date_from, date_to)
    return charts.receita_payload(dff, sel_events)


@app.get("/api/charts/marketing")
def marketing(user=Depends(current_user), events: str = "", channels: str = "Shotgun",
              date_from: str = "", date_to: str = ""):
    _, _, dff_sg, sel_events = _filtered(user, events, channels, date_from, date_to)
    return charts.marketing_payload(dff_sg, sel_events)


@app.get("/api/charts/audience")
def audience(user=Depends(current_user), events: str = "", channels: str = "Shotgun",
             date_from: str = "", date_to: str = ""):
    _, _, dff_sg, sel_events = _filtered(user, events, channels, date_from, date_to)
    return charts.audience_payload(dff_sg, sel_events)


@app.get("/api/charts/operacoes")
def operacoes(user=Depends(current_user), events: str = "", channels: str = "Shotgun",
              date_from: str = "", date_to: str = ""):
    dff, df_sel, dff_sg, sel_events = _filtered(user, events, channels, date_from, date_to)
    return charts.operacoes_payload(dff_sg, df_sel, sel_events)


# ── static front-end (mounted last so /api/* wins) ───────────────────────────
@app.get("/")
def index():
    return FileResponse(_FRONTEND / "index.html")


app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="static")
