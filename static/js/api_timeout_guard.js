(() => {
  if (window.__algoBotFetchGuard) return;
  const nativeFetch = window.fetch.bind(window);
  const API_LIMIT = 9000;
  const isApi = input => {
    try { const url = typeof input === 'string' ? input : input?.url; return new URL(url, location.origin).pathname.startsWith('/api/'); }
    catch (_) { return false; }
  };
  window.fetch = async (input, init = {}) => {
    if (!isApi(input) || init.__skipAlgoTimeout) return nativeFetch(input, init);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(new Error('API request timeout')), API_LIMIT);
    const callerSignal = init.signal;
    let signal = controller.signal;
    if (callerSignal) {
      signal = typeof AbortSignal.any === 'function' ? AbortSignal.any([callerSignal, controller.signal]) : controller.signal;
      if (callerSignal.aborted) controller.abort(callerSignal.reason);
    }
    try {
      return await nativeFetch(input, { ...init, signal });
    } catch (error) {
      if (controller.signal.aborted && !callerSignal?.aborted) {
        const timeout = new Error('AlgoBot API request timed out'); timeout.name = 'AlgoBotTimeoutError'; throw timeout;
      }
      throw error;
    } finally { clearTimeout(timer); }
  };
  window.__algoBotFetchGuard = true;
})();
