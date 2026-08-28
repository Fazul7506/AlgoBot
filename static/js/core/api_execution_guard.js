/* Shared API safety guard for execution requests. */
(() => {
  'use strict';
  if (window.__algoBotApiExecutionGuard) return;
  window.__algoBotApiExecutionGuard = true;
  const nativeFetch = window.fetch.bind(window);

  window.fetch = (input, init = {}) => {
    let url = typeof input === 'string' ? input : (input?.url || '');
    if (!url.includes('/api/') && url !== '/trading/order/' && url !== '/trading/preview/') return nativeFetch(input, init);
    if (init.signal) return nativeFetch(input, init);

    if (url === '/trading/order/') url = '/api/orders/';
    if (url === '/trading/preview/') url = '/api/orders/preview/';

    let nextInit = { ...init };
    if ((url.endsWith('/api/orders/') || url.endsWith('/api/orders/preview/')) && typeof nextInit.body === 'string') {
      try {
        const payload = JSON.parse(nextInit.body);
        payload.validation_context = {
          ...(payload.validation_context || {}),
          ...(window.__algobotAiOrderContext || {}),
        };
        nextInit.body = JSON.stringify(payload);
      } catch (_) {}
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    return nativeFetch(url, { ...nextInit, signal: controller.signal })
      .finally(() => clearTimeout(timer))
      .catch(error => {
        if (error?.name === 'AbortError') throw new Error('Backend request timed out after 12 seconds');
        throw error;
      });
  };
})();
