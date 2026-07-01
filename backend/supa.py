"""
Supabase access for the v2 backend.

- Config comes from env vars (SUPABASE_URL / SUPABASE_ANON_KEY) instead of
  Streamlit secrets.
- Auth is done client-side with supabase-js; the backend only *validates* the
  JWT and runs RLS-scoped queries using the user's access token, so the existing
  `user_id = auth.uid()` row-level-security policies still apply unchanged.
"""

import os
from pathlib import Path

from supabase import create_client, Client


def _load_dotenv() -> None:
    """Populate os.environ from backend/.env if present (no external dependency).

    Real environment variables always win; the file is only a fallback so local
    dev restarts don't need the keys re-pasted. The file is gitignored.
    """
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


_load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

_TICKETS = "shotgun_tickets"
_PORTA = "porta_entries"


def is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY)


# A single anon client is enough to validate tokens (auth.get_user(jwt)).
_anon: Client | None = None


def _anon_client() -> Client:
    global _anon
    if _anon is None:
        _anon = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return _anon


def get_user(jwt: str):
    """Validate the access token; return the supabase user or None."""
    if not jwt:
        return None
    try:
        return _anon_client().auth.get_user(jwt).user
    except Exception:
        return None


def client_for(jwt: str) -> Client:
    """A client whose PostgREST calls carry the user's JWT, so RLS applies."""
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    client.postgrest.auth(jwt)
    return client


# ── shotgun_tickets ────────────────────────────────────────────────────────────
def load_existing_ticket_ids(client: Client, user_id: str) -> set[str]:
    resp = client.table(_TICKETS).select("ticket_id").eq("user_id", user_id).execute()
    return {r["ticket_id"] for r in (resp.data or [])}


def upsert_tickets(client: Client, rows: list[dict]) -> None:
    if rows:
        client.table(_TICKETS).upsert(rows, on_conflict="user_id,ticket_id").execute()


def load_all_raw(client: Client, user_id: str) -> list[dict]:
    resp = client.table(_TICKETS).select("raw").eq("user_id", user_id).execute()
    return [row["raw"] for row in (resp.data or [])]


def delete_tickets(client: Client, user_id: str) -> None:
    client.table(_TICKETS).delete().eq("user_id", user_id).execute()


# ── porta_entries (extracted for later; not wired into v1 endpoints yet) ────────
def load_porta(client: Client, user_id: str) -> list[dict]:
    resp = (
        client.table(_PORTA).select("*")
        .eq("user_id", user_id).order("added_at").execute()
    )
    return [
        {
            "event_name":  r["event_name"],
            "tickets":     r["tickets"],
            "revenue_brl": float(r["revenue_brl"]),
            "source":      r["source"],
            "added_at":    r.get("added_at", ""),
            **({"prices": r["prices"]}     if r.get("prices")     else {}),
            **({"date":   r["entry_date"]} if r.get("entry_date") else {}),
        }
        for r in (resp.data or [])
    ]
