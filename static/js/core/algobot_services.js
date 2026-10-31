/* AlgoBot Service Facade
 *
 * Every frontend service uses this facade for shared transport, lifecycle,
 * account context, cancellation, retry and error reporting. Page scripts may
 * keep genuinely unique rendering/business logic, but must not create their
 * own transport/account infrastructure.
 */
(() => {
  'use strict';
  if (window.AlgoBotServices) return;

  const runtime = () => window.AlgoBotServiceRuntime;
  const context = () => window.AlgoBotAccountContext;
  const data = () => window.AlgoBotFrontendData;

  const accountId = () => context()?.getSelectedId?.() || window.AlgoBotBrokerState?.get?.()?.account?.id || null;
  const account = () => context()?.getSelected?.() || window.AlgoBotBrokerState?.get?.()?.account || null;

  const serviceFor = name => {
    const value = String(name || '').trim().toLowerCase();
    const aliases = {
      dashboard: 'dashboard',
      market: 'market-data', markets: 'market-data', scanner: 'market-data', instrument: 'market-data', instruments: 'market-data',
      order: 'orders', orders: 'orders',
      position: 'positions', positions: 'positions',
      trade: 'trading', terminal: 'trading', trading: 'trading',
      signal: 'signals', signals: 'signals',
      strategy: 'strategies', strategies: 'strategies',
      backtest: 'backtesting', backtesting: 'backtesting',
      prediction: 'predictions', predictions: 'predictions', ai: 'ai',
      risk: 'risk', monitoring: 'monitoring', notification: 'notifications',
      automation: 'automation', portfolio: 'portfolio', analytics: 'analytics',
      broker: 'brokers', brokers: 'brokers', developer: 'developer',
      billing: 'billing', operations: 'operations', data: 'market-data'
    };
    return aliases[value] || value || 'platform';
  };

  const register = (name, config = {}) => runtime()?.register(serviceFor(name), config) || null;

  const request = async (name, url, options = {}, timeout = 25000) => {
    const service = serviceFor(name);
    const requestOptions = { ...options, headers: { Accept: 'application/json', ...(options.headers || {}) } };
    try {
      if (data()?.request) return await data().request(url, { ...requestOptions, notifyOnError: false }, timeout);
      const response = await runtime()?.withTimeout?.(({ signal }) => fetch(url, { ...requestOptions, credentials: 'same-origin', signal }), timeout, service);
      if (!response) throw Object.assign(new Error('AlgoBot service runtime is not ready.'), { code: 'SERVICE_RUNTIME_UNAVAILABLE', retryable: true });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw Object.assign(new Error(payload?.detail || payload?.message || `Service request failed (${response.status}).`), { status: response.status, payload });
      return payload;
    } catch (error) {
      runtime()?.recordError?.({ service, url, method: requestOptions.method || 'GET', status: error?.status || 0, code: error?.code || 'SERVICE_REQUEST_ERROR', message: error?.message || 'Service request failed.', retryable: Boolean(error?.retryable ?? Number(error?.status) >= 500) });
      throw error;
    }
  };

  const run = (name, task, options = {}) => {
    const service = serviceFor(name);
    register(service, options.metadata || {});
    return runtime()?.run?.(service, task, options) || Promise.reject(Object.assign(new Error('AlgoBot service runtime is unavailable.'), { code: 'SERVICE_RUNTIME_UNAVAILABLE', retryable: true }));
  };

  const get = (name, url, options = {}, timeout) => request(name, url, { ...options, method: 'GET' }, timeout);
  const post = (name, url, body, options = {}, timeout) => request(name, url, { ...options, method: 'POST', headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, body: body == null ? undefined : JSON.stringify(body) }, timeout);
  const put = (name, url, body, options = {}, timeout) => request(name, url, { ...options, method: 'PUT', headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, body: body == null ? undefined : JSON.stringify(body) }, timeout);
  const patch = (name, url, body, options = {}, timeout) => request(name, url, { ...options, method: 'PATCH', headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, body: body == null ? undefined : JSON.stringify(body) }, timeout);
  const cancel = name => runtime()?.cancel?.(serviceFor(name));

  // One frontend instrument catalogue facade. The canonical transport owns
  // account scoping, in-flight deduplication, cache freshness and error handling.
  const instruments = Object.freeze({
    list: async (options = {}) => {
      const forceRefresh = Boolean(options.forceRefresh);
      const timeout = Number.isFinite(Number(options.timeout)) ? Number(options.timeout) : 7000;
      const notifyOnError = options.notifyOnError === true;
      const rowsFrom = payload => Array.isArray(payload?.symbols) ? payload.symbols
        : Array.isArray(payload?.results) ? payload.results
        : Array.isArray(payload?.data) ? payload.data
        : Array.isArray(payload?.markets) ? payload.markets
        : Array.isArray(payload) ? payload : [];
      let url = '/api/market/catalogue/' + (forceRefresh ? '?refresh=1' : '');
      let payload = await get('market-data', url, { notifyOnError }, timeout);
      let rows = rowsFrom(payload);

      // An empty first-run catalogue is refreshed asynchronously by the server.
      // Poll with unique query keys so the shared GET cache cannot replay the
      // initial 202 response while the broker sync is still running.
      for (let attempt = 0; !rows.length && payload?.refreshing === true && attempt < 4; attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        url = '/api/market/catalogue/?catalogue_poll=' + (attempt + 1);
        payload = await get('market-data', url, { notifyOnError }, timeout);
        rows = rowsFrom(payload);
      }

      return {
        ...(payload && typeof payload === 'object' && !Array.isArray(payload) ? payload : {}),
        symbols: rows,
        results: rows
      };
    },
    refresh: (options = {}) => instruments.list({ ...options, forceRefresh: true })
  });

  const services = Object.freeze({
    accountId, account, serviceFor, register, request, get, post, put, patch, run, cancel, instruments,
    runtime: () => runtime()?.snapshot?.() || null
  });

  window.AlgoBotServices = services;
  window.dispatchEvent(new CustomEvent('algobot:service-facade-ready'));
})();
