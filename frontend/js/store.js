// Alpine component: auth gate, sidebar filters, tab switching, chart orchestration.
document.addEventListener("alpine:init", () => {
  Alpine.data("app", () => ({
    ready: false,
    user: null,
    hasData: false,
    busy: false,
    toast: "",
    activeTab: "comparar",

    orgId: "",
    apiToken: "",

    summary: { events: [], date_min: null, date_max: null, channels: ["Shotgun"] },
    filters: { events: [], channels: ["Shotgun"], dateFrom: "", dateTo: "", refEvent: "" },
    kpis: { ingressos: 0, participantes: 0, receita: 0, comparecimento: 0, cancelamento: 0, newsletter: 0 },
    _loadedFor: null,

    async init() {
      try {
        // Listen for future sign-in / sign-out.
        await window.Auth.onChange((session) => this.onAuth(session));
        // Deterministic initial hydration: wait for the stored session, THEN load.
        const session = await window.Auth.getSession();
        await this.onAuth(session);
      } catch (e) {
        this.flash("Erro: " + e.message);
      }
      this.ready = true;
    },

    // Called from both the initial hydration and the onChange listener. Guarded by
    // `_loadedFor` so data loads exactly once per logged-in user (no double-load race).
    async onAuth(session) {
      const newUser = session ? { email: session.user.email, id: session.user.id } : null;
      this.user = newUser;
      if (!newUser) { this.hasData = false; this._loadedFor = null; return; }
      if (this._loadedFor !== newUser.id) {
        this._loadedFor = newUser.id;
        await this.loadData();
      }
    },

    // ── auth ──
    signIn() { window.Auth.signInGoogle(); },
    async signOut() { await window.Auth.signOut(); this.user = null; this.hasData = false; this._loadedFor = null; },

    // ── data ──
    async loadData() {
      try {
        const s = await window.API.summary();
        this.summary = s;
        this.hasData = !!s.loaded;
        if (!s.loaded) return;
        this.filters.events = [...s.events];
        this.filters.channels = s.channels.length ? s.channels : ["Shotgun"];
        this.filters.dateFrom = s.date_min || "";
        this.filters.dateTo = s.date_max || "";
        this.filters.refEvent = s.events[0] || "";
        await this.refresh();
      } catch (e) {
        this._loadedFor = null;        // allow a retry
        this.flash("Erro ao carregar dados: " + e.message);
      }
    },

    async fetchData() {
      if (!this.orgId || !this.apiToken) { this.flash("Informe o ID do organizador e o token."); return; }
      this.busy = true; this.flash("Buscando ingressos na API…");
      try {
        const r = await window.API.fetchTickets(this.orgId, this.apiToken);
        this.flash(`✓ ${r.n_new.toLocaleString("pt-BR")} novos · ${r.n_existing.toLocaleString("pt-BR")} já salvos.`);
        await this.loadData();
      } catch (e) { this.flash("Erro: " + e.message); }
      this.busy = false;
    },

    async clearData() {
      if (!confirm("Apagar todos os ingressos salvos?")) return;
      await window.API.clear();
      this.hasData = false;
      this.flash("Dados apagados.");
    },

    // ── filters ──
    get multi() { return this.filters.events.length > 1; },
    isSelected(ev) { return this.filters.events.includes(ev); },
    toggleEvent(ev) {
      const i = this.filters.events.indexOf(ev);
      if (i >= 0) this.filters.events.splice(i, 1); else this.filters.events.push(ev);
      if (!this.filters.events.includes(this.filters.refEvent))
        this.filters.refEvent = this.filters.events[0] || "";
      this.refresh();
    },
    selectAll() { this.filters.events = [...this.summary.events]; this.refresh(); },
    selectNone() { this.filters.events = []; this.refresh(); },

    setTab(t) { this.activeTab = t; this.$nextTick(() => this.renderActive()); },

    // ── render ──
    async refresh() {
      if (!this.hasData) return;
      try {
        this.kpis = await window.API.kpis(this.filters);
      } catch (e) { /* keep prior kpis */ }
      this.$nextTick(() => this.renderActive());
    },

    async renderActive() {
      if (!this.hasData) return;
      try {
        if (this.activeTab === "vendas") {
          window.renderVendas(await window.API.vendas(this.filters));
        } else if (this.activeTab === "comparar") {
          if (this.filters.events.length < 2) { window.Charts.clearAll(); return; }
          const data = await window.API.comparar(this.filters);
          if (data.ok) window.renderComparar(data);
        } else if (this.activeTab === "receita") {
          window.renderReceita(await window.API.receita(this.filters));
        } else if (this.activeTab === "marketing") {
          window.renderMarketing(await window.API.marketing(this.filters));
        } else if (this.activeTab === "publico") {
          window.renderAudience(await window.API.audience(this.filters));
        } else if (this.activeTab === "operacoes") {
          window.renderOperacoes(await window.API.operacoes(this.filters));
        }
        window.Charts.resizeAll();
      } catch (e) { this.flash("Erro ao carregar gráficos: " + e.message); }
    },

    flash(msg) {
      this.toast = msg;
      clearTimeout(this._t);
      this._t = setTimeout(() => (this.toast = ""), 4000);
    },

    fmtMoney(v) { return "R$" + Number(v).toLocaleString("pt-BR", { minimumFractionDigits: 2 }); },
  }));
});
