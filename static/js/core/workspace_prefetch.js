/* AlgoBot workspace performance layer.
 * Keeps broker-backed GET data warm across same-tab page navigation without
 * inventing data. Cached values are account-scoped and short-lived; network
 * revalidation is always performed in the background after a cache hit.
 *
 * The trading terminal owns its own bootstrap because it has live market,
 * contract and execution state. Prefetching those same resources globally
 * creates duplicate requests and account-switch races, so the terminal is
 * deliberately excluded here.
 */
(() => {
  'use strict';
  if (window.__algoBotWorkspacePrefetch) return;
  window.__algoBotWorkspacePrefetch = true;

  const data = () => window.AlgoBotFrontendData;
  const isTradingTerminal = () => document.body?.dataset?.algobotPage === 'trading-terminal' || !!document.querySelector('.terminal-page[data-page="trading-terminal"]');
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
  const clearAccount = previousId => {
    try {
      const prefix = `algobot:workspace-cache:v1:${previousId || accountId()}:`;
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
      if (isTradingTerminal() || method !== 'GET' || !safeGet.test(raw)) return originalRequest(url, options, timeout);

      const cached = read(raw);
      if (cached !== null) {
        void originalRequest(url, {...options, notifyOnError: false}, timeout)
          .then(payload => { write(raw, payload); window.dispatchEvent(new CustomEvent('algobot:workspace-cache-updated', {detail:{url:raw}})); })
          .catch(() => {});
        return cached;
      }
      const payload = await originalRequest(url, options, timeout);
      write(raw, payload);
      return payload;
    };
    Object.defineProperty(wrapped, '__algobotWorkspaceWrapped', {value:true});
    window.AlgoBotFrontendData = Object.freeze({...original, request: wrapped});
    return true;
  }

  function prefetch() {
    if (isTradingTerminal()) return;
    const api = data();
    if (!api?.request) return;
    const paths = [
      ['/api/brokers/accounts/', 9000],
      ['/api/market/catalogue/', 12000],
      ['/api/positions/open/', 8000],
      ['/api/orders/?limit=8', 8000],
      ['/api/dashboard/signals/?limit=8', 8000],
      ['/api/dashboard/account_overview/', 8000]
    ];
    paths.forEach(([url, timeout]) => {
      void api.request(url, {notifyOnError:false}, timeout).then(payload => write(url, payload)).catch(() => {});
    });
  }

  function boot() {
    if (!install()) {
      window.addEventListener('algobot:service-facade-ready', install, {once:true});
      setTimeout(install, 50);
    }
    const start = () => setTimeout(prefetch, 0);
    const resetCacheForSwitch = event => {
      const previousId = event.detail?.previousAccountId || event.detail?.previous?.id || null;
      if (previousId) clearAccount(previousId);
      start();
    };
    window.addEventListener('algobot:account-changed', resetCacheForSwitch);
    window.addEventListener('algobot:account-synced', resetCacheForSwitch);
    window.addEventListener('algobot:account-context-changed', resetCacheForSwitch);
    start();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true});
  else boot();
})();
