/* Shared API safety guard for execution requests. */
(() => {
  'use strict';
  if (window.__algoBotApiExecutionGuard) return;
  window.__algoBotApiExecutionGuard = true;
  const nativeFetch = window.fetch.bind(window);

  window.fetch = (input, init = {}) => {
    const url = typeof input === 'string' ? input : (input?.url || '');
    if (!url.includes('/api/') || init.signal) return nativeFetch(input, init);

    let nextInit = { ...init };
    if (url.endsWith('/api/orders/') && window.__algobotAiOrderContext && typeof nextInit.body === 'string') {
      try {
        const payload = JSON.parse(nextInit.body);
        payload.routing_context = { ...(payload.routing_context || {}), ...window.__algobotAiOrderContext };
        nextInit.body = JSON.stringify(payload);
        window.__algobotAiOrderContext = null;
      } catch (_) {}
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    return nativeFetch(input, { ...nextInit, signal: controller.signal })
      .finally(() => clearTimeout(timer))
      .catch(error => {
        if (error?.name === 'AbortError') throw new Error('Backend request timed out after 12 seconds');
        throw error;
      });
  };
})();
