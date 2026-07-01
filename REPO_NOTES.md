# Clubber Analytics — Repo Notes

Working reference for `dashboard.py`. Single-file Streamlit app for Shotgun (Brazilian
ticketing). UI is **100% Brazilian Portuguese**. Display name: **"Clubber Analytics"**.

> **Two versions live in this repo now:**
> - **v1 (production):** `dashboard.py` — Streamlit, deployed on Streamlit Cloud. Untouched by v2.
> - **v2:** `backend/` (FastAPI) + `frontend/` (Alpine.js + ECharts, no build). All 6 analytics
>   tabs ported (Porta tab still deferred). See the **v2 Architecture** section at the bottom.

> ⚠️ Line numbers drift as the file is edited. Treat them as approximate anchors —
> confirm with a quick grep before relying on a specific line.

## Run / validate

```bash
python -m streamlit run "dashboard.py"
# After every edit, syntax-check:
python -c "import ast, pathlib; ast.parse(pathlib.Path('dashboard.py').read_text(encoding='utf-8')); print('OK')"
```

## Files

| File | Purpose |
|---|---|
| `dashboard.py` | Entire app (~1,990 lines, no package structure) |
| `requirements.txt` | `streamlit`, `pandas`, `plotly`, `requests`, `supabase>=2.0.0` |
| `schema.sql` | 2 Postgres tables (`shotgun_tickets`, `porta_entries`), both RLS-scoped to `auth.uid()` |
| `.streamlit/secrets.toml` | gitignored Supabase creds (`[supabase]` url/key/redirect_url) |
| `.devcontainer/` | dev container config |

## Architecture

- **Data sources:** Shotgun API (`https://api.shotgun.live/tickets`, Bearer + `organizer_id`,
  paginated via `after` cursor), CSV upload, or Supabase DB (loaded on login).
- **Pipeline:** `fetch_tickets_from_api` / `load_csv` → `process(df)` → `st.session_state["df"]`
  → filtered `dff` → tabs. DB is single source of truth when logged in.
- **Incremental fetch:** "Buscar Dados" fetches all API tickets, diffs against existing
  `ticket_id`s in DB, upserts only new ones, then reloads full set from DB.
- **Charts:** Plotly (`px` + `go`).

### Key module-level state
`_SB_AVAIL` (supabase importable) · `_SB_MODE` (configured + client up) · `_sb` (Client) ·
`_sb_user` (User). `df` lives in `st.session_state`.

### Function map (`dashboard.py`)

| Function | Line | Purpose |
|---|---|---|
| `_pkce_pair` | 34 | PKCE verifier/challenge |
| `_api_get` | 75 | Single API GET |
| `fetch_tickets_from_api` | 97 | Paginated ticket pull |
| `_sanitize_for_json` / `_sanitize_record` | 121 / 139 | Make rows JSON-safe before jsonb upsert (NaT→None, Timestamp→ISO, np→py) |
| `process` | 145 | Parse datetime cols + derive fields |
| `load_csv` | 194 | CSV → DataFrame |
| `load_porta` / `save_porta` / `append_porta_entry` | 203 / 230 / 245 | Porta data CRUD (Supabase or local JSON) |
| `_read_pagbank` / `parse_pagbank_csv*` | 289 / 301 / 307 | PagBank CSV parsing |
| `porta_totals_by_event` / `expand_porta_to_rows` | 316 / 326 | Porta aggregation |
| `_sb_is_configured` | 377 | Secrets present? |
| `_render_login_page` | 386 | Google OAuth login UI |

### Datetime columns parsed in `process` (all UTC except birthday)
`ordered_at`, `event_start_time`, `event_end_time`, `ticket_scanned_at`,
`ticket_canceled_at`, `event_published_at`; `contact_birthday` is naive.

## Auth (Supabase + Google OAuth, PKCE)

- Auth gate is **unconditional** when Supabase is configured; missing secrets → error + stop.
- supabase-py v2 manages PKCE internally — **don't pass a manual `code_challenge`**.
  Extract its stored verifier, embed as `?sb_ver=` in `redirect_to`, then
  `exchange_code_for_session({"auth_code", "code_verifier"})`.
- `st.session_state` is lost on OAuth redirect AND on F5 refresh. Refresh token is mirrored
  into `st.query_params["_sb_rt"]` to survive refreshes; restore via
  `_sb.auth.refresh_session(rt)` (public, returns `AuthResponse` with `.user` — NOT
  `_call_refresh_token`). Logout calls `st.query_params.clear()`.
- **Critical indentation rule:** the post-login migration + DB-load block must be *outside*
  the `if _sb_user is None:` gate, or DB tickets never load on login.

## Tabs

Order: 📊 Comparar · 📈 Vendas · 💰 Receita · 📣 Marketing · 👥 Público · 🔍 Operações ·
🚪 Porta (conditional, only when Porta data exists).

Unpacked at line ~1066: `tab_compare, tab_sales, tab_revenue, tab_marketing, tab_audience,
tab_ops`. **Note:** code blocks are NOT in tab-label order — `with tab_sales:` comes first.

| Tab | `with` block |
|---|---|
| Vendas | ~1075 |
| Receita | ~1226 |
| Marketing | ~1329 |
| Público | ~1381 |
| Operações | ~1512 |
| Comparar | ~1632 |
| Porta | ~1900 |

### 📈 Vendas — visual inventory (~1075–1221)
1. Vendas Diárias por Evento — bar (multi vs single variant, ~1094 / ~1112)
2. Vendas Acumuladas — line (~1105 / ~1123)
3. Vendas por Dia da Semana — bar (~1140)
4. Quando as Pessoas Compraram? — bar, x-axis reversed (~1152)
5. Mapa de Calor: Dia da Semana × Hora — heatmap (~1168)
6. Resumo por Evento — dataframe table (~1205)

### 📊 Comparar — visual inventory (~1632–1894, needs ≥2 events)
Reference event highlighted orange `#FF7F0E`; others muted `#AAAAAA`.
- KPI row: Ingressos / Receita / % Pagos / Comparecimento vs média (~1662)
1. Receita por Evento — bar (~1680)
2. Ingressos Vendidos por Evento — bar (~1691)
3. Primeira Vez vs Recorrente — stacked bar (~1717)
4. Ingressos: Pago vs Gratuito — stacked bar (~1741)
5. Vendas Diárias: Selecionado vs Outros — line (~1776)
6. Vendas Acumuladas: Selecionado vs Outros — line (~1801)
7. Receita Diária: Selecionado vs Outros — line (~1846)
8. Receita Acumulada: Selecionado vs Outros — line (~1871)

> Charts 5–8 use x-axis **"Dias até o Evento"** (days until event =
> `event_start_date − order_date`, event day = 0 on the right via reversed axis).
> Falls back to "Dias desde a 1ª Venda" only if `event_start_time` is absent.
> The Vendas tab charts 1–2 use the same "Dias até o Evento" convention for multi-event
> (in **both** v1 and v2); single-event Vendas stays on calendar dates.

## Conventions (strict)

- **Single file only** — no new files/packages.
- **PT-BR only** — no English UI strings.
- **Vocabulary:** attendance is "Comparecimento / Presente / Ausente" (never "leitura/lidos").
  Free tickets (`deal_price_brl == 0`) → alias **"Gratuito"** and collapse into one bucket.
- **Charts:** "Distribuição por Status" = bar not pie; marketing channel = stacked bar
  (utm_medium × utm_source) not heatmap; "Quando compraram?" x-axis reversed (event day = 0
  on right); day-of-week via `_DOW_MAP` (Seg/Ter/Qua/Qui/Sex/Sáb/Dom).
- **KPI header:** 2 rows × 3 cols (not 1×6).
- **Conditional logic:** many charts hide/show on `len(sel_events)` (single vs multi event).
  Color palette constant: `COLORS`.
- Match existing Plotly/Streamlit patterns already in the file.

---

# v2 Architecture (FastAPI + Alpine/ECharts)

Second version: keeps Python as a data **backend**, replaces Streamlit UI with a custom
front-end. `dashboard.py` (v1) is left fully intact and still runs on Streamlit Cloud.

## Run v2 locally
```bash
pip install -r backend/requirements.txt
cd backend && python -m uvicorn main:app --reload --port 8000 --host 127.0.0.1
# open http://127.0.0.1:8000  (FastAPI serves the static frontend/ too)
```
**Config:** `supa.py` reads `SUPABASE_URL` / `SUPABASE_ANON_KEY` from the environment, and
falls back to a **gitignored `backend/.env`** (auto-loaded by `supa._load_dotenv()`, no
python-dotenv dependency). Real env vars win over the file. So local restarts need no keys —
just keep `backend/.env` present:
```
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_ANON_KEY=<anon public key>
```
The anon key is the **public** browser key (safe to store locally); it is NOT a session token.

Syntax check: `python -c "import ast,pathlib; ast.parse(pathlib.Path('backend/charts.py').read_text(encoding='utf-8'))"`

> **Origin gotcha:** localStorage (and the supabase session) is per-origin. Pick ONE of
> `127.0.0.1:8000` / `localhost:8000` and stick to it, and list it in Supabase → Auth →
> Redirect URLs, or logins won't persist across refresh.

## Layout
- `backend/core.py` — pure data fns copied verbatim from dashboard.py (no Streamlit):
  `fetch_tickets_from_api`, `process`, `_sanitize_record`, PagBank + Porta helpers, `COLORS`, `_DOW_MAP`.
- `backend/supa.py` — config via env vars **+ `backend/.env` fallback** (`_load_dotenv()`);
  `get_user(jwt)` validates token; `client_for(jwt)` runs RLS-scoped queries with the user's
  JWT; ticket select/upsert/delete + porta load.
- `backend/charts.py` — **the port of all Streamlit tab aggregations** → JSON. Functions:
  `build_df`, `apply_filters` (mirrors dashboard.py 990-1001), `compute_kpis`, `data_summary`,
  and one payload builder per tab:
  - `vendas_payload` — 6 visuals (Vendas charts 1–2 use "Dias até o Evento" multi-event).
  - `comparar_payload` — KPIs + 8 charts, incl. "Dias até o Evento" evolution via
    `_comparar_evolution` / `_add_dia`.
  - `receita_payload` — Receita por Evento (multi), por Categoria, Tipos Gratuitos, por Método
    de Pagamento, Gratuitos vs Pagos (donut), Receita Diária (single-event only).
  - `marketing_payload` — Canal de Aquisição (h-bar), Canal × Meio (stacked), Canal × Evento (multi).
  - `audience_payload` — Gênero, Idade (hist), Top 15 Cidades, Newsletter, Recorrentes (multi),
    Top 10 Fiéis (multi), Idade × Gênero.
  - `operacoes_payload` — Comparecimento (Pago/Gratuito × Presente/Ausente, `_SCAN_COLORS`),
    Cancelamento, Status, Mix de Categorias. Note: cancelamento/status use `df_sel`
    (includes canceled tickets), the rest use `dff` (Shotgun, non-canceled).
- `backend/main.py` — FastAPI. Routes: `GET /api/config` (public), `/api/me`,
  `POST /api/tickets/fetch`, `DELETE /api/tickets`, `/api/data/summary`, `/api/kpis`, and
  `/api/charts/{vendas,comparar,receita,marketing,audience,operacoes}`. The 4 tab endpoints
  share the `_filtered()` prelude (load → resolve events → `apply_filters`). Static mount serves
  `frontend/` — **defined last**, after all `@app.get`s, or the `/` catch-all swallows them.
  Auth = `Authorization: Bearer <jwt>` via `current_user` dependency.
- `frontend/` — `index.html` (Alpine root), `css/styles.css` (dark theme),
  `js/auth.js` (supabase-js Google OAuth — native session, no PKCE hacks),
  `js/api.js`, `js/store.js` (Alpine `app` component; `renderActive()` dispatches per tab),
  `js/charts/{base,vendas,comparar,receita,marketing,audience,operacoes}.js` (map payload →
  ECharts). All libs via CDN; **no build step**. Chart titles live in HTML `<h3>` card headers,
  NOT in ECharts options (avoids overlap with the y-axis unit label; keep `grid.top` ≈ 34).

## Data flow
supabase-js login → JWT → backend validates → loads user's `shotgun_tickets` from DB →
`process()` → `apply_filters` → aggregate → JSON → ECharts. Dataset re-loaded per request
(per-user in-memory cache is a future optimization).

## Status / out of scope
- **Done:** scaffold, auth, KPI header, sidebar filters, and **all 6 analytics tabs**
  end-to-end — Comparar, Vendas, Receita, Marketing, Público, Operações.
- **Deferred:** the 🚪 **Porta** tab (Porta/PagBank UI + CSV upload — functions extracted in
  `core.py`/`supa.py`, not yet wired to an endpoint or tab); guest mode (v2 requires Google login);
  per-user in-memory dataset cache (currently re-loaded per request).
- **Parity caveats vs v1 Plotly:** age charts are binned server-side (per-integer-age 16–80);
  "Idade × Gênero" is a stacked bar (v1 used overlay); a few multi-event-only cards
  (`r-diaria-card`, `m-canal-evento-card`, `a-recorrentes-card`, `a-top-card`) hide themselves
  via `display:none` when their payload key is absent.

## Deploy v2 (NOT Streamlit Cloud)
Single service on Render/Railway: FastAPI serves API + static front-end. Set `SUPABASE_URL` /
`SUPABASE_ANON_KEY` env vars. Add the deploy domain to Supabase → Auth → Redirect URLs.
