/* Runtime safety net for pages that depend on the shared frontend data contract. */
(() => {
  'use strict';
  if (window.AlgoBotFrontendData?.request) return;

  const list = value => Array.isArray(value)
    ? value
    : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));
  const csrf = () => document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || '';
  const isCloudflareChallenge = (response, text) => {
    const body = String(text || '').toLowerCase();
    const contentType = String(response.headers.get('content-type') || '').toLowerCase();
    return body.includes('just a moment...') || body.includes('cf_chl_opt') ||
      body.includes('challenges.cloudflare.com') || (contentType.includes('text/html') && response.status >= 403);
  };

  // Some production edge rules challenge AJAX requests under /api/. Keep the
  // canonical API intact, but retry the exact same authenticated request on
  // the edge-safe /data/ alias when Cloudflare returns its HTML challenge.
  const edgeFallback = url => {
    try {
      const parsed = new URL(url, window.location.origin);
      if (parsed.origin !== window.location.origin || !parsed.pathname.startsWith('/api/')) return null;
      parsed.pathname = `/data/${parsed.pathname.slice('/api/'.length)}`;
      return `${parsed.pathname}${parsed.search}${parsed.hash}`;
    } catch (_) { return null; }
  };

  async function requestOnce(url, options, timeout) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), Math.max(1000, timeout));
    try {
      const method = String(options.method || 'GET').toUpperCase();
      const headers = {Accept: 'application/json', ...(options.headers || {})};
      if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && !headers['X-CSRFToken']) headers['X-CSRFToken'] = csrf();
      const response = await fetch(url, {credentials: 'same-origin', ...options, headers, signal: controller.signal});
      const text = await response.text();
      return {response, text};
    } finally {
      clearTimeout(timer);
    }
  }

  async function request(url, options = {}, timeout = 25000) {
    if (!url) throw new Error('No API endpoint configured');
    let result;
    try {
      result = await requestOnce(url, options, timeout);
    } catch (error) {
      if (error?.name === 'AbortError') throw new Error('Backend request timed out');
      throw error;
    }

    const fallback = edgeFallback(url);
    if (fallback && isCloudflareChallenge(result.response, result.text)) {
      try {
        result = await requestOnce(fallback, options, timeout);
      } catch (error) {
        if (error?.name === 'AbortError') throw new Error('Backend request timed out');
        throw error;
      }
    }

    const {response, text} = result;
    let payload = {};
    try { payload = text ? JSON.parse(text) : {}; }
    catch (_) {
      const detail = isCloudflareChallenge(response, text)
        ? 'Production edge security challenged this API request. The edge-safe route also failed.'
        : text;
      payload = {detail};
    }
    if (!response.ok) throw new Error(payload.detail || payload.message || `Request failed (${response.status})`);
    return payload;
  }

  window.AlgoBotFrontendData = Object.freeze({request, list});
})();
