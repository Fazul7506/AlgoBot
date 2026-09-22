/* AlgoBot workspace performance layer.
 * Keeps broker-backed GET data warm across same-tab page navigation without
 * inventing data. Cached values are account-scoped and short-lived; network
 * revalidation is always performed in the background after a cache hit.
 */
(() => {
  'use strict';
  if (window.__algoBotWorkspacePrefetch) return;
  window.__algoBotWorkspacePrefetch = true;

  const data = () => window.AlgoBotFrontendData;
  const accountId = () => window.AlgoBotAccountContext?.getSelectedId?.() || window.AlgoBotBrokerState?.get?.()?.account?.id || 'none';
  const keyFor = url => `algobot:workspace-cache:v1:${accountId()}:${url}`;
  const safeGet = /^\/api\/(brokers\/accounts(?:\/|$)|market\/(?:catalogue|broker-capabilities|ticks\/broker|snapshots)|ticks\/latest|positions\/open|orders\/|dashboard\/(?:account_overview|signals)|signals\/|strategies\/)/;
  const ttlFor = url => {
    if (/ticks\/broker|ticks\/latest/.test(url)) return 3000;
    if (/market\/catalogue|broker-capabilities/.test(url)) return 120000;
    if (/orders\/|positions\/open|signals\//.test(url)) return 10000;
    return 30000;
  };
  const read = url => {
    try {
      const raw = sessionStorage.getItem(keyFor(url));
      if (!raw) return null;
      const item = JSON.parse(raw);
      if (!item || !Number.isFinite(item.at)) return null;
      if (Date.now() - item.at > ttlFor(url)) return null;
      return item.payload;
    } catch (_) { return null; }
  };
  const write = (url, payload) => {
    try {
      sessionStorage.setItem(keyFor(url), JSON.stringify({at: Date.now(), payload}));
    } catch (_) {}
  };
  const clearAccount = () => {
    try {
      const prefix = 'algobot:workspace-cache:v1:';
      for (let i = sessionStorage.length - 1; i >= 0; i--) {
        const k = sessionStorage.key(i);
        if (k?.startsWith(prefix)) sessionStorage.removeItem(k);
      }
    } catch (_) {}
  };

  function install() {
    const original = data();
    if (!original?.request || original.request.__algobotWorkspaceWrapped) return false;
    const originalRequest = original.request;
    const wrapped = async (url, options = {}, timeout = 25000) => {
      const method = String(options.method || 'GET').toUpperCase();
      const raw = String(url || '').split('#')[0];
      if (method !== 'GET' || !safeGet.test(raw)) return originalRequest(url, options, timeout);

      const cached = read(raw);
      if (cached !== null) return cached;
      const payload = await originalRequest(url, options, timeout);
      write(raw, payload);
      return payload;
    };
    Object.defineProperty(wrapped, '__algobotWorkspaceWrapped', {value:true});
    window.AlgoBotFrontendData = Object.freeze({...original, request: wrapped});
    return true;
  }

  function prefetch() {
    const api = data();
    if (!api?.request || document.visibilityState !== 'visible') return;
    // Never prefetch the Trading Terminal: it owns these resources and loads
    // them in the correct account/symbol order. Prefetching here caused a
    // duplicate request storm and made the terminal appear slow/unreliable.
    const path = window.location.pathname;
    if (path === '/trading/' || path.startsWith('/trading/')) return;
    // Keep global navigation light: warm only the account list. Page controllers
    // request their own data once they are mounted.
    const url = '/api/brokers/accounts/';
    if (read(url) !== null) return;
    void api.request(url, {notifyOnError:false}, 7000)
      .then(payload => write(url, payload))
      .catch(() => {});
  }

  function boot() {
    // Public pages must remain network-silent for authenticated workspace data.
    // In particular, never prefetch /api/brokers/accounts/ for a signed-out
    // visitor: a 401 is expected there, not a page error.
    if (document.body?.dataset.authenticated !== 'true') return;
    if (!install()) {
      window.addEventListener('algobot:service-facade-ready', install, {once:true});
      setTimeout(install, 50);
    }
    const start = () => setTimeout(prefetch, 0);
    window.addEventListener('algobot:account-changed', () => { clearAccount(); start(); });
    window.addEventListener('algobot:account-synced', () => { clearAccount(); start(); });
    window.addEventListener('algobot:account-context-changed', () => { clearAccount(); start(); });
    start();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true});
  else boot();
})();
