# Clubber Analytics — Repo Notes

Working reference for `dashboard.py`. Single-file Streamlit app for Shotgun (Brazilian
ticketing). UI is **100% Brazilian Portuguese**. Display name: **"Clubber Analytics"**.

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
> The Vendas tab (charts 1–2) still uses "Dias desde a 1ª Venda" for multi-event.

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
