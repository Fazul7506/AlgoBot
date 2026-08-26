(() => {
  'use strict';
  if (window.__algoBotFetchGuard) return;
  const nativeFetch = window.fetch.bind(window);
  const API_LIMIT = 30000;
  const isApi = input => {
    try {
      const url = typeof input === 'string' ? input : input?.url;
      return new URL(url, location.origin).pathname.startsWith('/api/');
    } catch (_) { return false; }
  };
  window.fetch = async (input, init = {}) => {
    if (!isApi(input) || init.__skipAlgoTimeout) return nativeFetch(input, init);
    const controller = new AbortController();
    const callerSignal = init.signal;
    const timeoutMs = Number.isFinite(Number(init.__algoTimeoutMs)) ? Math.max(1000, Number(init.__algoTimeoutMs)) : API_LIMIT;
    const timer = setTimeout(() => controller.abort(new Error('API request timeout')), timeoutMs);
    const signal = callerSignal && typeof AbortSignal.any === 'function'
      ? AbortSignal.any([callerSignal, controller.signal])
      : controller.signal;
    if (callerSignal?.aborted) controller.abort(callerSignal.reason);
    try {
      return await nativeFetch(input, { ...init, signal });
    } catch (error) {
      if (controller.signal.aborted && !callerSignal?.aborted) {
        const timeout = new Error(`AlgoBot API request timed out after ${timeoutMs}ms`);
        timeout.name = 'AlgoBotTimeoutError';
        timeout.code = 'API_TIMEOUT';
        throw timeout;
      }
      throw error;
    } finally { clearTimeout(timer); }
  };
  window.__algoBotFetchGuard = true;
})();
