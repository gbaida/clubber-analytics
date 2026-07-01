// Thin fetch wrappers. Every call attaches the Supabase access token as a
// Bearer header; the backend validates it and scopes queries via RLS.

window.API = (function () {
  async function _headers() {
    const token = await window.Auth.getToken();
    return token ? { Authorization: "Bearer " + token } : {};
  }

  async function _get(path, params) {
    const url = new URL(path, window.location.origin);
    if (params) Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    });
    const res = await fetch(url, { headers: await _headers() });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    return res.json();
  }

  async function _send(method, path, body) {
    const res = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json", ...(await _headers()) },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    return res.json();
  }

  // filters → query params (events/channels are "|"-joined)
  function _q(filters) {
    return {
      events: (filters.events || []).join("|"),
      channels: (filters.channels || ["Shotgun"]).join("|"),
      date_from: filters.dateFrom || "",
      date_to: filters.dateTo || "",
    };
  }

  return {
    me:        () => _get("/api/me"),
    summary:   () => _get("/api/data/summary"),
    kpis:      (f) => _get("/api/kpis", _q(f)),
    vendas:    (f) => _get("/api/charts/vendas", _q(f)),
    comparar:  (f) => _get("/api/charts/comparar", { ..._q(f), ref_event: f.refEvent || "" }),
    receita:   (f) => _get("/api/charts/receita", _q(f)),
    marketing: (f) => _get("/api/charts/marketing", _q(f)),
    audience:  (f) => _get("/api/charts/audience", _q(f)),
    operacoes: (f) => _get("/api/charts/operacoes", _q(f)),
    fetchTickets: (organizer_id, token) => _send("POST", "/api/tickets/fetch", { organizer_id, token }),
    clear:     () => _send("DELETE", "/api/tickets"),
  };
})();
