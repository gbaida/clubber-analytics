// Supabase client-side auth (Google OAuth). supabase-js handles the OAuth
// redirect + session persistence in localStorage natively, so none of the
// PKCE/token-in-URL hacks from the Streamlit version are needed here.

window.Auth = (function () {
  let client = null;

  async function init() {
    if (client) return client;
    const cfg = await fetch("/api/config").then((r) => r.json());
    if (!cfg.supabase_url || !cfg.supabase_anon_key) {
      throw new Error("Supabase não configurado no servidor (env vars).");
    }
    client = window.supabase.createClient(cfg.supabase_url, cfg.supabase_anon_key, {
      auth: {
        flowType: "pkce",
        detectSessionInUrl: true,
        persistSession: true,
        autoRefreshToken: true,
        storage: window.localStorage,
        storageKey: "clubber-auth",
      },
    });
    // Defensive: after the OAuth redirect supabase-js exchanges the code and
    // stores the session; strip leftover ?code=/#tokens so a later refresh of
    // that URL can't try to re-exchange an already-used code (which logs you out).
    if (/[?#].*(code=|access_token=)/.test(window.location.href)) {
      await client.auth.getSession();
      history.replaceState({}, document.title, window.location.pathname);
    }
    return client;
  }

  async function getSession() {
    await init();
    const { data } = await client.auth.getSession();
    return data.session || null;
  }

  async function getToken() {
    const s = await getSession();
    return s ? s.access_token : null;
  }

  async function signInGoogle() {
    await init();
    await client.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin },
    });
  }

  async function signOut() {
    await init();
    await client.auth.signOut();
  }

  async function onChange(cb) {
    await init();
    client.auth.onAuthStateChange((_event, session) => cb(session));
  }

  return { init, getSession, getToken, signInGoogle, signOut, onChange };
})();
