/* Runtime safety net for pages that depend on the shared frontend data contract. */
(() => {
  'use strict';
  if (window.AlgoBotFrontendData?.request) return;

  const list = value => Array.isArray(value)
    ? value
    : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));
  const csrf = () => document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || '';

  async function request(url, options = {}, timeout = 25000) {
    if (!url) throw new Error('No API endpoint configured');
    const method = String(options.method || 'GET').toUpperCase();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), Math.max(1000, timeout));
    try {
      const headers = {Accept: 'application/json', ...(options.headers || {})};
      if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && !headers['X-CSRFToken']) headers['X-CSRFToken'] = csrf();
      const response = await fetch(url, {credentials: 'same-origin', ...options, headers, signal: controller.signal});
      const text = await response.text();
      let payload = {};
      try { payload = text ? JSON.parse(text) : {}; } catch (_) { payload = {detail: text}; }
      if (!response.ok) throw new Error(payload.detail || payload.message || `Request failed (${response.status})`);
      return payload;
    } catch (error) {
      if (error?.name === 'AbortError') throw new Error('Backend request timed out');
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  window.AlgoBotFrontendData = Object.freeze({request, list});
})();
