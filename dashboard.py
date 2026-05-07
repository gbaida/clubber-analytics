"""
Shotgun Event Analytics Dashboard
Run with: python -m streamlit run dashboard.py
"""

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(
    page_title="Shotgun Analytics",
    page_icon="🎟️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    div[data-testid="metric-container"] {
        background: #0e1117;
        border: 1px solid #2a2a3a;
        border-radius: 10px;
        padding: 16px 20px;
    }
    div[data-testid="metric-container"] label { color: #9a9ab0 !important; font-size: 13px; }
    div[data-testid="metric-container"] [data-testid="stMetricValue"] { font-size: 26px; }
</style>
""", unsafe_allow_html=True)

COLORS = px.colors.qualitative.Plotly
DEFAULT_CSV = Path("")

_DOW_ORDER  = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_DOW_MAP    = dict(zip(_DOW_ORDER, ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]))

# ── API fetch logic ────────────────────────────────────────────────────────────

_TICKETS_URL = "https://api.shotgun.live/tickets"
_TIMEOUT     = 60
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


def fetch_tickets_from_api(token: str, organizer_id: str, progress=None) -> pd.DataFrame:
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
        if progress:
            progress.text(f"Buscando... {len(all_records):,} ingressos encontrados")
        if not records or not next_url:
            break
        cursor = _parse_after(next_url)

    return pd.DataFrame(all_records)


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
        df["order_date"] = df["ordered_at"].dt.date
        df["order_hour"] = df["ordered_at"].dt.hour
        df["order_dow"]  = df["ordered_at"].dt.day_name()

    return df


@st.cache_data
def load_csv(source) -> pd.DataFrame:
    return process(pd.read_csv(source))


# ── Sidebar esquerda — fonte de dados ─────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎟️ Shotgun Analytics")
    st.caption("feito por [ponkan](https://linktr.ee/ponkan_)")

    if "df" in st.session_state:
        if st.button("🚪 Limpar dados", use_container_width=True):
            del st.session_state["df"]
            st.session_state.pop("source_label", None)
            st.rerun()

    st.divider()

    st.markdown("### Buscar via API")
    st.caption("[Como descobrir os seus dados de API](https://support-pro.shotgun.live/hc/en-us/articles/33561354477970-Find-your-Organizer-id-and-API-token#h_01KJ7K6DYV1FWN0AD6NRV5W1XE)")
    api_token    = st.text_input("Token de API", type="password", placeholder="eyJhbGci...")
    organizer_id = st.text_input("ID do Organizador", placeholder="123456")

    if st.button("🔄 Buscar Dados", use_container_width=True, type="primary"):
        if not api_token or not organizer_id:
            st.error("Preencha o Token de API e o ID do Organizador.")
        else:
            prog = st.empty()
            try:
                with st.spinner("Conectando à API do Shotgun..."):
                    raw = fetch_tickets_from_api(api_token, organizer_id, progress=prog)
                st.session_state["df"] = process(raw)
                st.session_state["source_label"] = f"API ao vivo — {len(raw):,} ingressos"
                prog.empty()
                st.success(f"{len(raw):,} ingressos carregados com sucesso.")
            except requests.Timeout as e:
                st.error(f"⏱️ {e}")
            except requests.HTTPError as e:
                st.error(f"Erro na API {e.response.status_code}: {e.response.text[:200]}")
            except Exception as e:
                st.error(f"Erro: {e}")

    st.divider()

    st.markdown("### Ou envie um arquivo CSV")
    uploaded = st.file_uploader("CSV", type="csv", label_visibility="collapsed")
    if uploaded:
        st.session_state["df"] = load_csv(uploaded)
        st.session_state["source_label"] = f"CSV — {uploaded.name}"

    if "df" not in st.session_state:
        if DEFAULT_CSV.is_file():
            st.session_state["df"] = load_csv(str(DEFAULT_CSV))
            st.session_state["source_label"] = f"Arquivo local — {DEFAULT_CSV.name}"
        else:
            st.info("Insira seus dados de API ou envie um CSV para começar.")

    if "df" in st.session_state:
        st.caption(f"Fonte: {st.session_state.get('source_label', '')}")

    st.divider()
    st.caption("Gostou? Pix e sugestões para gustavobaida@gmail.com")


# ── Tela de boas-vindas ────────────────────────────────────────────────────────
if "df" not in st.session_state:
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown(
            "<h1 style='text-align:center'>🎟️ Shotgun Analytics</h1>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p style='text-align:center; color:#9a9ab0; margin-bottom:0.5rem'>"
            "Painel de análise de eventos conectado diretamente à API do Shotgun.</p>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p style='text-align:center; color:#9a9ab0; margin-bottom:2rem'>"
            "feito por <a href='https://linktr.ee/ponkan_' target='_blank'>ponkan</a></p>",
            unsafe_allow_html=True,
        )
        st.markdown("""
**O que você pode analisar:**

- 📈 **Vendas** — evolução diária, dias de venda e comportamento de compra antes do evento
- 💰 **Receita** — por categoria de ingresso, método de pagamento e ao longo do tempo
- 📣 **Marketing** — quais canais (Instagram, Direct, Shotgun App...) geraram mais vendas
- 👥 **Público** — gênero, faixa etária, cidades e taxa de opt-in na newsletter
- 🔍 **Operações** — taxa de comparecimento e cancelamentos por evento

---

**Como começar:**

1. Acesse o **Shotgun Smartboard** → Configurações → Integrações → APIs do Shotgun
2. Copie seu **Token de API** e **ID do Organizador**
3. Cole os dados na barra lateral e clique em **🔄 Buscar Dados**

Ou envie um arquivo `.csv` exportado anteriormente diretamente pela barra lateral.
""")
    st.stop()


# ── Layout principal: conteúdo + filtros à direita ────────────────────────────
df = st.session_state["df"]
col_main, col_filters = st.columns([5, 1])

# ── Filtros (coluna direita) ───────────────────────────────────────────────────
with col_filters:
    st.markdown("### Filtros")

    # Checklist de eventos
    st.markdown("**Eventos**")
    events_info = (
        df[["event_id", "event_name"]].drop_duplicates()
        .sort_values("event_name").reset_index(drop=True)
    )
    ca, cb = st.columns(2)
    if ca.button("✅ Todos", use_container_width=True):
        for eid in events_info["event_id"].tolist():
            st.session_state[f"evt_{eid}"] = True
        st.rerun()
    if cb.button("☐ Nenhum", use_container_width=True):
        for eid in events_info["event_id"].tolist():
            st.session_state[f"evt_{eid}"] = False
        st.rerun()

    box_h = min(260, len(events_info) * 28 + 16)
    sel_events = []
    with st.container(height=box_h):
        for _, row in events_info.iterrows():
            key = f"evt_{row['event_id']}"
            if key not in st.session_state:
                st.session_state[key] = True
            if st.checkbox(row["event_name"], key=key, help=f"ID: {row['event_id']}"):
                sel_events.append(row["event_name"])

    if not sel_events:
        sel_events = events_info["event_name"].tolist()

    # Período de compra
    st.markdown("**Período de compra**")
    valid_dates = df["order_date"].dropna() if "order_date" in df.columns else pd.Series([], dtype=object)
    if not valid_dates.empty:
        min_d = valid_dates.min()
        max_d = valid_dates.max()
        if min_d < max_d:
            date_range = st.slider(
                "Período", min_value=min_d, max_value=max_d,
                value=(min_d, max_d), format="DD/MM/YY",
                label_visibility="collapsed",
            )
        else:
            date_range = (min_d, max_d)
    else:
        date_range = None

    # Status
    st.markdown("**Status do ingresso**")
    all_statuses = sorted(df["ticket_status"].dropna().unique())
    sel_statuses = st.multiselect(
        "Status", all_statuses,
        default=[s for s in all_statuses if s != "canceled"],
        label_visibility="collapsed",
    )

# ── Aplicar filtros ────────────────────────────────────────────────────────────
mask = df["event_name"].isin(sel_events) & df["ticket_status"].isin(sel_statuses)
if date_range and "order_date" in df.columns:
    mask &= df["order_date"].between(date_range[0], date_range[1])
dff    = df[mask].copy()
df_sel = df[df["event_name"].isin(sel_events)].copy()


# ── Conteúdo principal (coluna esquerda) ──────────────────────────────────────
with col_main:

    if dff.empty:
        st.warning("Nenhum ingresso encontrado para os filtros selecionados.")
        st.stop()

    # ── KPIs ──────────────────────────────────────────────────────────────────
    total_tickets    = len(dff)
    unique_attendees = dff["contact_id"].nunique()
    total_revenue    = dff["deal_price_brl"].sum() if "deal_price_brl" in dff else 0
    total_canceled   = (df_sel["ticket_status"] == "canceled").sum()
    cancel_rate      = total_canceled / len(df_sel) * 100 if len(df_sel) else 0
    scanned          = dff["ticket_scanned_at"].notna().sum()
    scan_rate        = scanned / total_tickets * 100 if total_tickets else 0
    newsletter_rate  = (
        dff["contact_newsletter_optin"].sum() / dff["contact_newsletter_optin"].notna().sum() * 100
        if "contact_newsletter_optin" in dff and dff["contact_newsletter_optin"].notna().sum() > 0
        else 0
    )

    st.markdown("## Visão Geral")
    c1, c2, c3 = st.columns(3)
    c4, c5, c6 = st.columns(3)
    c1.metric("Ingressos Vendidos",     f"{total_tickets:,}")
    c2.metric("Participantes Únicos",   f"{unique_attendees:,}")
    c3.metric("Receita Total",          f"R${total_revenue:,.2f}")
    c4.metric("Taxa de Comparecimento", f"{scan_rate:.1f}%")
    c5.metric("Taxa de Cancelamento",   f"{cancel_rate:.1f}%")
    c6.metric("Opt-in Newsletter",      f"{newsletter_rate:.1f}%")

    st.divider()

    # ── Abas ──────────────────────────────────────────────────────────────────
    tab_compare, tab_sales, tab_revenue, tab_marketing, tab_audience, tab_ops = st.tabs([
        "📊 Comparar", "📈 Vendas", "💰 Receita", "📣 Marketing", "👥 Público", "🔍 Operações"
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # ABA 1 — VENDAS
    # ══════════════════════════════════════════════════════════════════════════
    with tab_sales:
        st.subheader("Vendas de Ingressos ao Longo do Tempo")

        if "order_date" in dff.columns:
            col_l, col_r = st.columns(2)
            multi = len(sel_events) > 1

            daily = (
                dff.groupby(["order_date", "event_name"])
                .size().reset_index(name="ingressos")
            )
            daily["order_date"] = pd.to_datetime(daily["order_date"])
            daily = daily.sort_values("order_date")

            if multi:
                first_sale = daily.groupby("event_name")["order_date"].min().rename("first_sale")
                daily = daily.merge(first_sale, on="event_name")
                daily["dias_desde_inicio"] = (daily["order_date"] - daily["first_sale"]).dt.days

                fig = px.bar(
                    daily, x="dias_desde_inicio", y="ingressos", color="event_name",
                    labels={"dias_desde_inicio": "Dias desde a 1ª Venda", "ingressos": "Ingressos Vendidos", "event_name": "Evento"},
                    title="Vendas Diárias por Evento (desde a 1ª venda)",
                    color_discrete_sequence=COLORS,
                )
                fig.update_layout(legend=dict(orientation="h", y=-0.2), bargap=0.15)
                col_l.plotly_chart(fig, use_container_width=True)

                cum = daily.copy()
                cum["acumulado"] = cum.groupby("event_name")["ingressos"].cumsum()
                fig2 = px.line(
                    cum, x="dias_desde_inicio", y="acumulado", color="event_name",
                    labels={"dias_desde_inicio": "Dias desde a 1ª Venda", "acumulado": "Ingressos Acumulados", "event_name": "Evento"},
                    title="Vendas Acumuladas de Ingressos (desde a 1ª venda)",
                    color_discrete_sequence=COLORS, markers=True,
                )
            else:
                fig = px.bar(
                    daily, x="order_date", y="ingressos", color="event_name",
                    labels={"order_date": "Data", "ingressos": "Ingressos Vendidos", "event_name": "Evento"},
                    title="Vendas Diárias por Evento",
                    color_discrete_sequence=COLORS,
                )
                fig.update_layout(legend=dict(orientation="h", y=-0.2), bargap=0.15)
                col_l.plotly_chart(fig, use_container_width=True)

                cum = daily.copy()
                cum["acumulado"] = cum.groupby("event_name")["ingressos"].cumsum()
                fig2 = px.line(
                    cum, x="order_date", y="acumulado", color="event_name",
                    labels={"order_date": "Data", "acumulado": "Ingressos Acumulados", "event_name": "Evento"},
                    title="Vendas Acumuladas de Ingressos",
                    color_discrete_sequence=COLORS, markers=True,
                )

            fig2.update_layout(legend=dict(orientation="h", y=-0.2))
            col_r.plotly_chart(fig2, use_container_width=True)

        col_l2, col_r2 = st.columns(2)

        if "order_dow" in dff.columns:
            dow = dff.groupby("order_dow").size().reset_index(name="ingressos")
            dow["order_dow"] = pd.Categorical(dow["order_dow"], categories=_DOW_ORDER, ordered=True)
            dow = dow.sort_values("order_dow")
            dow["dia"] = dow["order_dow"].map(_DOW_MAP)
            fig3 = px.bar(
                dow, x="dia", y="ingressos",
                labels={"dia": "Dia da Semana", "ingressos": "Ingressos Vendidos"},
                title="Vendas por Dia da Semana",
                color_discrete_sequence=[COLORS[0]],
            )
            col_l2.plotly_chart(fig3, use_container_width=True)

        if "days_before_event" in dff.columns:
            dff_pre = dff[dff["days_before_event"] >= 0].copy()
            dff_pre["days_before_bucket"] = dff_pre["days_before_event"].clip(upper=30).astype(int)
            pre_counts = dff_pre.groupby("days_before_bucket").size().reset_index(name="ingressos")
            fig4 = px.bar(
                pre_counts.sort_values("days_before_bucket", ascending=False),
                x="days_before_bucket", y="ingressos",
                labels={"days_before_bucket": "Dias Antes do Evento", "ingressos": "Ingressos Vendidos"},
                title="Quando as Pessoas Compraram? (Dias Antes do Evento)",
                color_discrete_sequence=[COLORS[2]],
            )
            fig4.update_xaxes(autorange="reversed")
            col_r2.plotly_chart(fig4, use_container_width=True)

        if "order_hour" in dff.columns and "order_dow" in dff.columns:
            heat = dff.groupby(["order_dow", "order_hour"]).size().reset_index(name="ingressos")
            heat["order_dow"] = pd.Categorical(heat["order_dow"], categories=_DOW_ORDER, ordered=True)
            heat = heat.sort_values("order_dow")
            pivot_heat = heat.pivot(index="order_dow", columns="order_hour", values="ingressos").fillna(0)
            pivot_heat.index = [_DOW_MAP[d] for d in pivot_heat.index]
            fig_heat = px.imshow(
                pivot_heat,
                labels=dict(x="Hora do Dia", y="Dia da Semana", color="Ingressos"),
                title="Mapa de Calor: Dia da Semana × Hora",
                color_continuous_scale="Blues", text_auto=True,
                aspect="auto",
            )
            st.plotly_chart(fig_heat, use_container_width=True)

        st.subheader("Resumo por Evento")

        event_dates = df_sel.groupby("event_name").agg(
            primeira_venda=("order_date", "min"),
            data_evento=("event_start_time", "min"),
        ).reset_index()
        if "event_start_time" in df_sel.columns:
            event_dates["dias_de_vendas"] = (
                event_dates["data_evento"].dt.tz_convert(None).dt.normalize()
                - pd.to_datetime(event_dates["primeira_venda"])
            ).dt.days
        else:
            event_dates["dias_de_vendas"] = None

        summary = (
            df_sel.groupby("event_name").agg(
                total=("ticket_id", "count"),
                validos=("ticket_status", lambda x: (x == "valid").sum()),
                cancelados=("ticket_status", lambda x: (x == "canceled").sum()),
                lidos=("ticket_scanned_at", lambda x: x.notna().sum()),
                receita=("deal_price_brl", "sum"),
            ).reset_index()
        )
        summary = summary.merge(event_dates[["event_name", "dias_de_vendas"]], on="event_name", how="left")
        summary["taxa_presenca"]     = (summary["lidos"] / summary["validos"] * 100).round(1).astype(str) + "%"
        summary["taxa_cancelamento"] = (summary["cancelados"] / summary["total"] * 100).round(1).astype(str) + "%"
        summary["receita"]           = summary["receita"].map("R${:,.2f}".format)
        summary = summary[["event_name", "total", "validos", "cancelados", "lidos", "receita", "dias_de_vendas", "taxa_presenca", "taxa_cancelamento"]]
        summary.columns = ["Evento", "Total", "Válidos", "Cancelados", "Comparecimento", "Receita", "Dias de Venda", "Taxa de Comparecimento", "Taxa de Cancelamento"]
        st.dataframe(summary, use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════════
    # ABA 2 — RECEITA
    # ══════════════════════════════════════════════════════════════════════════
    with tab_revenue:
        if "deal_price_brl" not in dff.columns:
            st.info("Dados de preço não disponíveis.")
        else:
            col_l, col_r = st.columns(2)

            if len(sel_events) > 1:
                vol_ev = (
                    dff.groupby("event_name")
                    .agg(receita=("deal_price_brl", "sum"))
                    .reset_index().sort_values("receita", ascending=False)
                )
                fig2 = px.bar(
                    vol_ev, x="event_name", y="receita",
                    labels={"event_name": "Evento", "receita": "Receita (BRL)"},
                    title="Receita por Evento",
                    color="event_name", color_discrete_sequence=COLORS,
                    text="receita",
                )
                fig2.update_traces(texttemplate="R$%{text:,.0f}", textposition="outside")
                fig2.update_layout(showlegend=False, xaxis_tickangle=-20)
                col_l.plotly_chart(fig2, use_container_width=True)

            dff["deal_title_display"] = dff["deal_title"].where(dff["deal_price_brl"] > 0, "Gratuito")
            rev_tier = (
                dff.groupby("deal_title_display")
                .agg(ingressos=("ticket_id", "count"), receita=("deal_price_brl", "sum"))
                .reset_index().sort_values("receita", ascending=False)
            )
            fig = px.bar(
                rev_tier, x="deal_title_display", y="receita",
                labels={"deal_title_display": "Categoria de Ingresso", "receita": "Receita (BRL)"},
                title="Receita por Categoria de Ingresso",
                color="deal_title_display", color_discrete_sequence=COLORS, text="receita",
            )
            fig.update_traces(texttemplate="R$%{text:,.0f}", textposition="outside")
            fig.update_layout(showlegend=False, xaxis_tickangle=-20)
            col_r.plotly_chart(fig, use_container_width=True)

            free_tickets = dff[dff["deal_price_brl"] == 0]
            if not free_tickets.empty:
                free_counts = free_tickets.groupby("deal_title").size().reset_index(name="ingressos")
                fig_free = px.bar(
                    free_counts.sort_values("ingressos", ascending=False),
                    x="deal_title", y="ingressos",
                    labels={"deal_title": "Tipo de Ingresso Gratuito", "ingressos": "Ingressos"},
                    title="Tipos de Ingresso Gratuito",
                    color="deal_title", color_discrete_sequence=COLORS, text="ingressos",
                )
                fig_free.update_traces(textposition="outside")
                fig_free.update_layout(showlegend=False, xaxis_tickangle=-20)
                st.plotly_chart(fig_free, use_container_width=True)

            col_l2, col_r2 = st.columns(2)

            if "payment_method" in dff.columns:
                pay = (
                    dff[dff["deal_price_brl"] > 0]
                    .groupby("payment_method")
                    .agg(ingressos=("ticket_id", "count"), receita=("deal_price_brl", "sum"))
                    .reset_index()
                )
                pay["payment_method"] = pay["payment_method"].replace({"": "outro"}).fillna("outro")
                fig3 = px.bar(
                    pay, x="payment_method", y="receita",
                    labels={"payment_method": "Método de Pagamento", "receita": "Receita (BRL)"},
                    title="Receita por Método de Pagamento",
                    color="payment_method", color_discrete_sequence=COLORS, text="receita",
                )
                fig3.update_traces(texttemplate="R$%{text:,.0f}", textposition="outside")
                fig3.update_layout(showlegend=False)
                col_l2.plotly_chart(fig3, use_container_width=True)

            dff["tipo_ingresso"] = dff["deal_price_brl"].apply(lambda x: "Gratuito" if x == 0 else "Pago")
            fp = dff["tipo_ingresso"].value_counts().reset_index()
            fp.columns = ["tipo", "quantidade"]
            fig4 = px.pie(
                fp, names="tipo", values="quantidade",
                title="Ingressos Gratuitos vs Pagos",
                color_discrete_sequence=COLORS, hole=0.4,
            )
            fig4.update_traces(textinfo="percent+value")
            col_r2.plotly_chart(fig4, use_container_width=True)

            if "order_date" in dff.columns and len(sel_events) == 1:
                rev_daily = (
                    dff.groupby(["order_date", "event_name"])["deal_price_brl"]
                    .sum().reset_index()
                )
                rev_daily["order_date"] = pd.to_datetime(rev_daily["order_date"])
                fig5 = px.area(
                    rev_daily.sort_values("order_date"),
                    x="order_date", y="deal_price_brl", color="event_name",
                    labels={"order_date": "Data", "deal_price_brl": "Receita (BRL)", "event_name": "Evento"},
                    title="Receita Diária ao Longo do Tempo",
                    color_discrete_sequence=COLORS,
                )
                fig5.update_layout(legend=dict(orientation="h", y=-0.2))
                st.plotly_chart(fig5, use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════════
    # ABA 3 — MARKETING
    # ══════════════════════════════════════════════════════════════════════════
    with tab_marketing:
        col_l, col_r = st.columns(2)

        if "utm_source" in dff.columns:
            src = dff["utm_source"].value_counts().reset_index()
            src.columns = ["canal", "ingressos"]
            fig = px.bar(
                src, x="ingressos", y="canal", orientation="h",
                labels={"canal": "Canal de Aquisição", "ingressos": "Ingressos"},
                title="Ingressos por Canal de Aquisição",
                color="canal", color_discrete_sequence=COLORS, text="ingressos",
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(showlegend=False, yaxis={"categoryorder": "total ascending"})
            col_l.plotly_chart(fig, use_container_width=True)

        if "utm_source" in dff.columns and "utm_medium" in dff.columns:
            src_med = (
                dff.groupby(["utm_source", "utm_medium"])
                .size().reset_index(name="ingressos")
            )
            fig_stk = px.bar(
                src_med, x="utm_source", y="ingressos", color="utm_medium",
                barmode="stack",
                labels={"utm_source": "Canal de Aquisição", "ingressos": "Ingressos", "utm_medium": "Meio"},
                title="Canal × Meio (App vs Web)",
                color_discrete_sequence=COLORS,
            )
            fig_stk.update_layout(
                xaxis={"categoryorder": "total descending"},
                legend=dict(orientation="h", y=-0.25),
            )
            col_r.plotly_chart(fig_stk, use_container_width=True)

        if len(sel_events) > 1 and "utm_source" in dff.columns:
            src_ev = dff.groupby(["event_name", "utm_source"]).size().reset_index(name="ingressos")
            fig4 = px.bar(
                src_ev, x="event_name", y="ingressos", color="utm_source",
                barmode="group",
                labels={"event_name": "Evento", "ingressos": "Ingressos", "utm_source": "Canal"},
                title="Performance por Canal e Evento",
                color_discrete_sequence=COLORS,
            )
            fig4.update_layout(legend=dict(orientation="h", y=-0.25), xaxis_tickangle=-20)
            st.plotly_chart(fig4, use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════════
    # ABA 4 — PÚBLICO
    # ══════════════════════════════════════════════════════════════════════════
    with tab_audience:
        col_l, col_r = st.columns(2)

        if "contact_gender" in dff.columns:
            gender = (
                dff.drop_duplicates("contact_id")["contact_gender"]
                .replace({"-": None, "": None}).dropna()
                .value_counts().reset_index()
            )
            gender.columns = ["genero", "quantidade"]
            fig = px.pie(
                gender, names="genero", values="quantidade",
                title="Gênero do Público",
                color_discrete_sequence=COLORS, hole=0.4,
            )
            fig.update_traces(textinfo="percent+label")
            col_l.plotly_chart(fig, use_container_width=True)

        if "age" in dff.columns:
            ages = dff.drop_duplicates("contact_id")["age"].dropna()
            ages = ages[(ages >= 16) & (ages <= 80)]
            fig2 = px.histogram(
                ages, x="age", nbins=30,
                labels={"age": "Idade", "count": "Participantes"},
                title="Distribuição de Idade dos Participantes",
                color_discrete_sequence=["#636EFA"],
            )
            fig2.update_layout(bargap=0.05)
            col_r.plotly_chart(fig2, use_container_width=True)

        col_l2, col_r2 = st.columns(2)

        if "contact_locality" in dff.columns:
            cities = (
                dff.drop_duplicates("contact_id")["contact_locality"]
                .replace({"-": None, "01008-000": None, "": None}).dropna()
                .value_counts().head(15).reset_index()
            )
            cities.columns = ["cidade", "participantes"]
            fig3 = px.bar(
                cities, x="participantes", y="cidade", orientation="h",
                labels={"cidade": "Cidade", "participantes": "Participantes"},
                title="Top 15 Cidades",
                color_discrete_sequence=[COLORS[0]], text="participantes",
            )
            fig3.update_traces(textposition="outside")
            fig3.update_layout(yaxis={"categoryorder": "total ascending"})
            col_l2.plotly_chart(fig3, use_container_width=True)

        if "contact_newsletter_optin" in dff.columns:
            optin = (
                dff.drop_duplicates("contact_id")["contact_newsletter_optin"]
                .map({True: "Inscrito", False: "Não Inscrito"})
                .dropna().value_counts().reset_index()
            )
            optin.columns = ["status", "quantidade"]
            fig4 = px.pie(
                optin, names="status", values="quantidade",
                title="Taxa de Opt-in Newsletter",
                color_discrete_sequence=COLORS, hole=0.4,
            )
            fig4.update_traces(textinfo="percent+value")
            col_r2.plotly_chart(fig4, use_container_width=True)

        if len(sel_events) > 1:
            st.subheader("Fidelidade do Público")
            events_per_contact = dff.groupby("contact_id")["event_id"].nunique().reset_index()
            events_per_contact.columns = ["contact_id", "eventos_frequentados"]
            loyalty = events_per_contact["eventos_frequentados"].value_counts().reset_index()
            loyalty.columns = ["eventos_frequentados", "participantes"]
            loyalty["label"] = loyalty["eventos_frequentados"].apply(
                lambda x: f"{x} evento{'s' if x > 1 else ''}"
            )
            fig5 = px.bar(
                loyalty.sort_values("eventos_frequentados"),
                x="label", y="participantes",
                labels={"label": "Eventos Frequentados", "participantes": "Participantes"},
                title="Participantes Recorrentes",
                color_discrete_sequence=[COLORS[2]], text="participantes",
            )
            fig5.update_traces(textposition="outside")
            st.plotly_chart(fig5, use_container_width=True)

        if len(sel_events) > 1:
            st.subheader("Top 10 — Participantes Mais Fiéis")
            name_col = next((c for c in ["contact_name", "contact_email"] if c in dff.columns), None)
            top = (
                dff.groupby("contact_id")["event_id"].nunique()
                .reset_index(name="eventos")
                .sort_values("eventos", ascending=False)
                .head(10)
            )
            if name_col:
                top = top.merge(
                    dff[["contact_id", name_col]].drop_duplicates("contact_id"),
                    on="contact_id", how="left",
                )
                display_col = name_col
            else:
                display_col = "contact_id"
            fig_top = px.bar(
                top, x="eventos", y=display_col, orientation="h",
                labels={display_col: "Participante", "eventos": "Eventos Frequentados"},
                title="Top 10 Participantes por Eventos Frequentados",
                color_discrete_sequence=[COLORS[3]], text="eventos",
            )
            fig_top.update_traces(textposition="outside")
            fig_top.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_top, use_container_width=True)

        if "age" in dff.columns and "contact_gender" in dff.columns:
            age_gen = (
                dff.drop_duplicates("contact_id")[["age", "contact_gender"]]
                .replace({"-": None, "": None}).dropna()
            )
            age_gen = age_gen[(age_gen["age"] >= 16) & (age_gen["age"] <= 80)]
            fig6 = px.histogram(
                age_gen, x="age", color="contact_gender", nbins=25,
                barmode="overlay", opacity=0.75,
                labels={"age": "Idade", "contact_gender": "Gênero"},
                title="Distribuição de Idade por Gênero",
                color_discrete_sequence=COLORS,
            )
            st.plotly_chart(fig6, use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════════
    # ABA 5 — OPERAÇÕES
    # ══════════════════════════════════════════════════════════════════════════
    with tab_ops:
        col_l, col_r = st.columns(2)

        dff["_ticket_type"] = (
            dff["deal_price_brl"].apply(lambda x: "Gratuito" if x == 0 else "Pago")
            if "deal_price_brl" in dff.columns
            else "Pago"
        )

        scan_ev = dff.groupby(["event_name", "_ticket_type"]).agg(
            total=("ticket_id", "count"),
            presentes=("ticket_scanned_at", lambda x: x.notna().sum()),
        ).reset_index()
        scan_ev["ausentes"] = scan_ev["total"] - scan_ev["presentes"]

        events_order = (
            scan_ev.groupby("event_name")["total"].sum()
            .sort_values(ascending=False).index.tolist()
        )

        _SCAN_COLORS = {
            ("Pago",     "Presente"): "#00CC96",
            ("Pago",     "Ausente"):  "#EF553B",
            ("Gratuito", "Presente"): "#72EFDD",
            ("Gratuito", "Ausente"):  "#FF9F7F",
        }

        fig = go.Figure()
        for ttype in ["Pago", "Gratuito"]:
            sub = scan_ev[scan_ev["_ticket_type"] == ttype]
            if sub.empty:
                continue
            for status, col_name in [("Presente", "presentes"), ("Ausente", "ausentes")]:
                fig.add_trace(go.Bar(
                    name=f"{ttype} – {status}",
                    x=sub["event_name"],
                    y=sub[col_name],
                    marker_color=_SCAN_COLORS[(ttype, status)],
                    text=sub[col_name],
                    textposition="inside",
                    offsetgroup=ttype,
                ))
        fig.update_layout(
            barmode="stack", title="Comparecimento por Evento",
            xaxis={"categoryorder": "array", "categoryarray": events_order, "tickangle": -20},
            legend=dict(orientation="h", y=-0.3),
        )
        col_l.plotly_chart(fig, use_container_width=True)

        cancel_ev = (
            df_sel.groupby("event_name").agg(
                total=("ticket_id", "count"),
                cancelados=("ticket_status", lambda x: (x == "canceled").sum()),
            ).reset_index()
        )
        cancel_ev["taxa_cancelamento"] = cancel_ev["cancelados"] / cancel_ev["total"] * 100
        fig2 = px.bar(
            cancel_ev, x="event_name", y="taxa_cancelamento",
            labels={"event_name": "Evento", "taxa_cancelamento": "Taxa de Cancelamento (%)"},
            title="Taxa de Cancelamento por Evento",
            color_discrete_sequence=[COLORS[1]],
            text=cancel_ev["taxa_cancelamento"].round(1).astype(str) + "%",
        )
        fig2.update_traces(textposition="outside")
        fig2.update_layout(xaxis_tickangle=-20)
        col_r.plotly_chart(fig2, use_container_width=True)

        status_counts = df_sel["ticket_status"].value_counts().reset_index()
        status_counts.columns = ["status", "quantidade"]
        fig3 = px.bar(
            status_counts, x="status", y="quantidade",
            labels={"status": "Status", "quantidade": "Ingressos"},
            title="Distribuição por Status de Ingresso",
            color="status", color_discrete_sequence=COLORS, text="quantidade",
        )
        fig3.update_traces(textposition="outside")
        fig3.update_layout(showlegend=False)
        col_l.plotly_chart(fig3, use_container_width=True)

        if "deal_price_brl" in dff.columns:
            dff["deal_category"] = dff["deal_title"].where(dff["deal_price_brl"] > 0, "Gratuito")
        else:
            dff["deal_category"] = dff["deal_title"]
        tier_ev = dff.groupby(["event_name", "deal_category"]).size().reset_index(name="ingressos")
        fig4 = px.bar(
            tier_ev, x="event_name", y="ingressos", color="deal_category",
            barmode="stack",
            labels={"event_name": "Evento", "ingressos": "Ingressos", "deal_category": "Categoria"},
            title="Mix de Categorias por Evento",
            color_discrete_sequence=COLORS,
        )
        fig4.update_layout(xaxis_tickangle=-20, legend=dict(orientation="h", y=-0.3))
        col_r.plotly_chart(fig4, use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════════
    # ABA 6 — COMPARAR EVENTO
    # ══════════════════════════════════════════════════════════════════════════
    with tab_compare:
        if len(sel_events) < 2:
            st.info("Selecione pelo menos 2 eventos no filtro lateral para usar a comparação.")
        else:
            _HL   = "#FF7F0E"
            _MUTE = "#AAAAAA"

            ref_event = st.selectbox(
                "Evento de referência",
                sorted(sel_events),
                key="compare_ref_event",
            )

            dff_ref   = dff[dff["event_name"] == ref_event]
            other_evs = [e for e in sel_events if e != ref_event]

            # ── KPIs: selecionado vs média dos outros ─────────────────────────
            def _ev_kpis(d):
                total   = len(d)
                receita = d["deal_price_brl"].sum() if "deal_price_brl" in d.columns else 0
                pago    = (d["deal_price_brl"] > 0).mean() * 100 if "deal_price_brl" in d.columns else 0
                scan    = d["ticket_scanned_at"].notna().mean() * 100
                return total, receita, pago, scan

            ref_k  = _ev_kpis(dff_ref)
            avg_k  = tuple(
                sum(_ev_kpis(dff[dff["event_name"] == e])[i] for e in other_evs) / len(other_evs)
                for i in range(4)
            )

            st.markdown(f"### ⭐ {ref_event}")
            ck1, ck2, ck3, ck4 = st.columns(4)
            ck1.metric("Ingressos Vendidos",    f"{ref_k[0]:,}",          f"{ref_k[0]-avg_k[0]:+.0f} vs média")
            ck2.metric("Receita Total",          f"R${ref_k[1]:,.2f}",     f"R${ref_k[1]-avg_k[1]:+,.2f} vs média")
            ck3.metric("% Ingressos Pagos",      f"{ref_k[2]:.1f}%",       f"{ref_k[2]-avg_k[2]:+.1f}pp vs média")
            ck4.metric("Taxa de Comparecimento", f"{ref_k[3]:.1f}%",       f"{ref_k[3]-avg_k[3]:+.1f}pp vs média")

            st.divider()

            # ── Receita e Ingressos por evento (cor do destaque) ──────────────
            ev_sum   = dff.groupby("event_name").agg(
                receita=("deal_price_brl", "sum"),
                ingressos=("ticket_id", "count"),
            ).reset_index()
            disc_map = {e: (_HL if e == ref_event else _MUTE) for e in sel_events}

            col_l, col_r = st.columns(2)

            fig_rev = px.bar(
                ev_sum.sort_values("receita", ascending=False),
                x="event_name", y="receita", color="event_name",
                color_discrete_map=disc_map, text="receita",
                labels={"event_name": "Evento", "receita": "Receita (BRL)"},
                title="Receita por Evento",
            )
            fig_rev.update_traces(texttemplate="R$%{text:,.0f}", textposition="outside")
            fig_rev.update_layout(showlegend=False, xaxis_tickangle=-20)
            col_l.plotly_chart(fig_rev, use_container_width=True)

            fig_tix = px.bar(
                ev_sum.sort_values("ingressos", ascending=False),
                x="event_name", y="ingressos", color="event_name",
                color_discrete_map=disc_map, text="ingressos",
                labels={"event_name": "Evento", "ingressos": "Ingressos Vendidos"},
                title="Ingressos Vendidos por Evento",
            )
            fig_tix.update_traces(textposition="outside")
            fig_tix.update_layout(showlegend=False, xaxis_tickangle=-20)
            col_r.plotly_chart(fig_tix, use_container_width=True)

            # ── Pago vs Gratuito (stacked, borda laranja no selecionado) ──────
            col_l2, col_r2 = st.columns(2)

            # First-timers vs returning across all events
            contacts_by_ev = dff.groupby("event_name")["contact_id"].apply(set)
            loyalty_rows = []
            for ev in sel_events:
                ev_c    = contacts_by_ev.get(ev, set())
                other_c = set().union(*[contacts_by_ev.get(e, set()) for e in sel_events if e != ev])
                loyalty_rows.append({"event_name": ev, "tipo": "Primeira Vez", "participantes": len(ev_c - other_c)})
                loyalty_rows.append({"event_name": ev, "tipo": "Recorrente",   "participantes": len(ev_c & other_c)})
            loyalty_df = pd.DataFrame(loyalty_rows)

            ev_ord_l  = ev_sum.sort_values("ingressos", ascending=False)["event_name"].tolist()
            ref_pos_l = ev_ord_l.index(ref_event)
            fig_loyal = px.bar(
                loyalty_df, x="event_name", y="participantes", color="tipo",
                barmode="stack",
                category_orders={"event_name": ev_ord_l},
                color_discrete_map={"Primeira Vez": COLORS[4], "Recorrente": COLORS[5]},
                labels={"event_name": "Evento", "participantes": "Participantes", "tipo": ""},
                title="Primeira Vez vs Recorrente por Evento",
            )
            fig_loyal.add_shape(
                type="rect", xref="x", yref="paper",
                x0=ref_pos_l - 0.45, x1=ref_pos_l + 0.45, y0=0, y1=1,
                line=dict(color=_HL, width=3), fillcolor="rgba(0,0,0,0)",
            )
            fig_loyal.update_layout(xaxis_tickangle=-20, legend=dict(orientation="h", y=-0.25))
            col_l2.plotly_chart(fig_loyal, use_container_width=True)

            if "deal_price_brl" in dff.columns:
                dff["_ctype"] = dff["deal_price_brl"].apply(lambda x: "Gratuito" if x == 0 else "Pago")
                type_grp = dff.groupby(["event_name", "_ctype"]).agg(
                    ingressos=("ticket_id", "count"),
                ).reset_index()

                ev_ord_t  = ev_sum.sort_values("ingressos", ascending=False)["event_name"].tolist()
                ref_pos_t = ev_ord_t.index(ref_event)
                fig_tt = px.bar(
                    type_grp, x="event_name", y="ingressos", color="_ctype",
                    barmode="stack",
                    category_orders={"event_name": ev_ord_t},
                    color_discrete_map={"Pago": COLORS[0], "Gratuito": COLORS[2]},
                    labels={"event_name": "Evento", "ingressos": "Ingressos", "_ctype": "Tipo"},
                    title="Ingressos: Pago vs Gratuito",
                )
                fig_tt.add_shape(
                    type="rect", xref="x", yref="paper",
                    x0=ref_pos_t - 0.45, x1=ref_pos_t + 0.45, y0=0, y1=1,
                    line=dict(color=_HL, width=3), fillcolor="rgba(0,0,0,0)",
                )
                fig_tt.update_layout(xaxis_tickangle=-20, legend=dict(orientation="h", y=-0.25))
                col_r2.plotly_chart(fig_tt, use_container_width=True)

            # ── Vendas ao longo do tempo ───────────────────────────────────────
            if "order_date" in dff.columns:
                st.divider()

                daily = dff.groupby(["order_date", "event_name"]).size().reset_index(name="ingressos")
                daily["order_date"] = pd.to_datetime(daily["order_date"])
                fs = daily.groupby("event_name")["order_date"].min().rename("first_sale")
                daily = daily.merge(fs, on="event_name")
                daily["dia"] = (daily["order_date"] - daily["first_sale"]).dt.days
                daily["acumulado"] = daily.groupby("event_name")["ingressos"].cumsum()

                ref_d = daily[daily["event_name"] == ref_event]
                avg_d = (
                    daily[daily["event_name"] != ref_event]
                    .groupby("dia")[["ingressos", "acumulado"]].mean().reset_index()
                )

                col_l3, col_r3 = st.columns(2)

                fig_day = go.Figure()
                for ev in other_evs:
                    ev_d = daily[daily["event_name"] == ev]
                    fig_day.add_trace(go.Scatter(
                        x=ev_d["dia"], y=ev_d["ingressos"], mode="lines",
                        line=dict(color=_MUTE, width=1), opacity=0.4,
                        showlegend=False, name=ev,
                    ))
                fig_day.add_trace(go.Scatter(
                    x=avg_d["dia"], y=avg_d["ingressos"], mode="lines",
                    line=dict(color=_MUTE, width=2, dash="dash"),
                    name="Média dos outros",
                ))
                fig_day.add_trace(go.Scatter(
                    x=ref_d["dia"], y=ref_d["ingressos"], mode="lines+markers",
                    line=dict(color=_HL, width=3), name=ref_event,
                ))
                fig_day.update_layout(
                    title="Vendas Diárias: Selecionado vs Outros",
                    xaxis_title="Dias desde a 1ª Venda",
                    yaxis_title="Ingressos",
                    legend=dict(orientation="h", y=-0.25),
                )
                col_l3.plotly_chart(fig_day, use_container_width=True)

                fig_cum = go.Figure()
                for ev in other_evs:
                    ev_d = daily[daily["event_name"] == ev]
                    fig_cum.add_trace(go.Scatter(
                        x=ev_d["dia"], y=ev_d["acumulado"], mode="lines",
                        line=dict(color=_MUTE, width=1), opacity=0.4,
                        showlegend=False, name=ev,
                    ))
                fig_cum.add_trace(go.Scatter(
                    x=avg_d["dia"], y=avg_d["acumulado"], mode="lines",
                    line=dict(color=_MUTE, width=2, dash="dash"),
                    name="Média dos outros",
                ))
                fig_cum.add_trace(go.Scatter(
                    x=ref_d["dia"], y=ref_d["acumulado"], mode="lines+markers",
                    line=dict(color=_HL, width=3), name=ref_event,
                ))
                fig_cum.update_layout(
                    title="Vendas Acumuladas: Selecionado vs Outros",
                    xaxis_title="Dias desde a 1ª Venda",
                    yaxis_title="Ingressos Acumulados",
                    legend=dict(orientation="h", y=-0.25),
                )
                col_r3.plotly_chart(fig_cum, use_container_width=True)

            # ── Receita ao longo do tempo ──────────────────────────────────────
            if "deal_price_brl" in dff.columns and "order_date" in dff.columns:
                daily_rev = (
                    dff.groupby(["order_date", "event_name"])["deal_price_brl"]
                    .sum().reset_index(name="receita")
                )
                daily_rev["order_date"] = pd.to_datetime(daily_rev["order_date"])
                fs_r = daily_rev.groupby("event_name")["order_date"].min().rename("first_sale")
                daily_rev = daily_rev.merge(fs_r, on="event_name")
                daily_rev["dia"] = (daily_rev["order_date"] - daily_rev["first_sale"]).dt.days
                daily_rev["receita_acum"] = daily_rev.groupby("event_name")["receita"].cumsum()

                ref_r = daily_rev[daily_rev["event_name"] == ref_event]
                avg_r = (
                    daily_rev[daily_rev["event_name"] != ref_event]
                    .groupby("dia")[["receita", "receita_acum"]].mean().reset_index()
                )

                col_l4, col_r4 = st.columns(2)

                fig_rday = go.Figure()
                for ev in other_evs:
                    ev_r = daily_rev[daily_rev["event_name"] == ev]
                    fig_rday.add_trace(go.Scatter(
                        x=ev_r["dia"], y=ev_r["receita"], mode="lines",
                        line=dict(color=_MUTE, width=1), opacity=0.4,
                        showlegend=False, name=ev,
                    ))
                fig_rday.add_trace(go.Scatter(
                    x=avg_r["dia"], y=avg_r["receita"], mode="lines",
                    line=dict(color=_MUTE, width=2, dash="dash"),
                    name="Média dos outros",
                ))
                fig_rday.add_trace(go.Scatter(
                    x=ref_r["dia"], y=ref_r["receita"], mode="lines+markers",
                    line=dict(color=_HL, width=3), name=ref_event,
                ))
                fig_rday.update_layout(
                    title="Receita Diária: Selecionado vs Outros",
                    xaxis_title="Dias desde a 1ª Venda",
                    yaxis_title="Receita (BRL)",
                    legend=dict(orientation="h", y=-0.25),
                )
                col_l4.plotly_chart(fig_rday, use_container_width=True)

                fig_racum = go.Figure()
                for ev in other_evs:
                    ev_r = daily_rev[daily_rev["event_name"] == ev]
                    fig_racum.add_trace(go.Scatter(
                        x=ev_r["dia"], y=ev_r["receita_acum"], mode="lines",
                        line=dict(color=_MUTE, width=1), opacity=0.4,
                        showlegend=False, name=ev,
                    ))
                fig_racum.add_trace(go.Scatter(
                    x=avg_r["dia"], y=avg_r["receita_acum"], mode="lines",
                    line=dict(color=_MUTE, width=2, dash="dash"),
                    name="Média dos outros",
                ))
                fig_racum.add_trace(go.Scatter(
                    x=ref_r["dia"], y=ref_r["receita_acum"], mode="lines+markers",
                    line=dict(color=_HL, width=3), name=ref_event,
                ))
                fig_racum.update_layout(
                    title="Receita Acumulada: Selecionado vs Outros",
                    xaxis_title="Dias desde a 1ª Venda",
                    yaxis_title="Receita Acumulada (BRL)",
                    legend=dict(orientation="h", y=-0.25),
                )
                col_r4.plotly_chart(fig_racum, use_container_width=True)
