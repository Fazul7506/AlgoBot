/* Shared API safety guard for execution and AI requests. */
(() => {
  'use strict';
  if (window.__algoBotApiExecutionGuard) return;
  window.__algoBotApiExecutionGuard = true;
  const nativeFetch = window.fetch.bind(window);
  const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);
  const aliases = {
    '/trading/order/': '/api/orders/',
    '/trading/preview/': '/api/orders/preview/',
    '/trading/ai/predict/': '/api/ai/predict/',
  };

  const csrfToken = () => {
    const cookie = document.cookie.split(';').map(v => v.trim()).find(v => v.startsWith('csrftoken='));
    if (cookie) return decodeURIComponent(cookie.slice('csrftoken='.length));
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
  };

  window.fetch = (input, init = {}) => {
    let url = typeof input === 'string' ? input : (input?.url || '');
    if (!url.includes('/api/') && !aliases[url]) return nativeFetch(input, init);
    if (init.signal) return nativeFetch(input, init);
    url = aliases[url] || url;

    let nextInit = { ...init, credentials: init.credentials || 'include' };
    const method = String(nextInit.method || 'GET').toUpperCase();
    const headers = new Headers(nextInit.headers || {});
    headers.set('Accept', headers.get('Accept') || 'application/json');
    if (!SAFE_METHODS.has(method) && !headers.has('X-CSRFToken')) {
      const token = csrfToken();
      if (token) headers.set('X-CSRFToken', token);
    }
    nextInit.headers = headers;

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
