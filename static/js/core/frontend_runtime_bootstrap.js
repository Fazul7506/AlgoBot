/* Runtime safety net for pages that depend on the shared frontend data contract. */
(() => {
  'use strict';
  if (window.AlgoBotFrontendData?.request) return;

  const list = value => Array.isArray(value)
    ? value
    : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));

  // Prefer Django's rendered token over a potentially stale cookie. This is
  // especially important when the browser page and API are served from
  // different hosts and therefore have different CSRF-cookie state.
  const csrf = () => {
    const meta = document.querySelector('meta[name="csrf-token"]')?.content || '';
    if (meta && meta !== 'NOTPROVIDED') return meta;
    return document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || '';
  };

  const configuredApiBase = (document.querySelector('meta[name="algobot-api-base"]')?.content || '').trim();
  const defaultApiBase = window.location.hostname === 'algobot.dpdns.org' ? 'https://api.algobot.dpdns.org' : '';
  const apiBase = (configuredApiBase || defaultApiBase).replace(/\/+$/, '');
  const resolveUrl = url => /^https?:\/\//i.test(url) ? url : `${apiBase}${url.startsWith('/') ? url : `/${url}`}`;

  const isCloudflareChallenge = (response, text) => {
    const body = String(text || '').toLowerCase();
    const contentType = String(response?.headers?.get('content-type') || '').toLowerCase();
    return [400,403,429,503,520,521,522,524].includes(response?.status) &&
      (body.includes('just a moment') || body.includes('cf_chl_opt') || body.includes('challenge-platform') || body.includes('challenges.cloudflare.com') || body.includes('enable javascript and cookies to continue') || (body.includes('cloudflare') && contentType.includes('text/html')));
  };

  const isCsrfFailure = (response, text) => {
    if (response?.status !== 403) return false;
    const body = String(text || '').toLowerCase();
    return body.includes('csrf') || body.includes('cross site request forgery') || body.includes('forbidden (csrf');
  };

  const parse = (response, text) => {
    try { return text ? JSON.parse(text) : {}; }
    catch (_) { return {detail:isCloudflareChallenge(response,text) ? 'Production edge security challenged this API request.' : `Backend returned an unexpected response (${response?.status || 'unknown'}).`}; }
  };

  async function requestOnce(url, options, timeout, sameOrigin = false, csrfOverride = '') {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), Math.max(1000, timeout));
    try {
      const method = String(options.method || 'GET').toUpperCase();
      const headers = {Accept:'application/json', ...(options.headers || {})};
      if (!['GET','HEAD','OPTIONS'].includes(method) && !headers['X-CSRFToken']) {
        headers['X-CSRFToken'] = csrfOverride || csrf();
      }
      const target = sameOrigin ? url : resolveUrl(url);
      const crossOrigin = (() => { try { return new URL(target, window.location.origin).origin !== window.location.origin; } catch (_) { return false; } })();
      const response = await fetch(target,{credentials:crossOrigin ? 'include' : 'same-origin',...options,headers,signal:controller.signal});
      return {response,text:await response.text()};
    } finally { clearTimeout(timer); }
  }

  async function request(url, options = {}, timeout = 25000) {
    if (!url) throw new Error('No API endpoint configured');
    let result;
    try {
      result = await requestOnce(url, options, timeout);

      // The page can have a valid Django token while the dedicated API host
      // has a different/stale CSRF cookie. A CSRF 403 is safe to retry once
      // through the existing same-origin /api route using the page's rendered
      // token. Never retry arbitrary mutations, only a confirmed CSRF failure.
      if (isCsrfFailure(result.response, result.text) && apiBase && !/^https?:\/\//i.test(url)) {
        try {
          const fallback = await requestOnce(url, options, timeout, true, csrf());
          if (fallback.response.ok || !isCsrfFailure(fallback.response, fallback.text)) result = fallback;
        } catch (_) { /* preserve the original response for diagnostics */ }
      }

      // A Cloudflare/browser challenge is an edge response, not an application
      // response. When the API hostname is challenged, retry relative API paths
      // against the same-origin Render service instead of surfacing a false
      // backend failure. Only challenge responses are retried, so application
      // 4xx/5xx responses and mutation errors are never duplicated.
      if (isCloudflareChallenge(result.response, result.text) && apiBase && !/^https?:\/\//i.test(url)) {
        try {
          const fallback = await requestOnce(url, options, timeout, true, csrf());
          if (!isCloudflareChallenge(fallback.response, fallback.text)) result = fallback;
        } catch (_) { /* preserve the original edge response for diagnostics */ }
      }
    } catch (error) {
      // If the dedicated hostname has not propagated yet, preserve application
      // availability by falling back to the existing same-origin API path.
      if (apiBase && !/^https?:\/\//i.test(url) && error?.name !== 'AbortError') {
        try { result = await requestOnce(url, options, timeout, true, csrf()); } catch (_) { result = null; }
      }
      if (!result) {
        if (error?.name === 'AbortError') throw new Error('Backend request timed out');
        throw error;
      }
    }

    const {response,text} = result;
    const payload = parse(response,text);
    if (!response.ok) {
      const error = new Error(payload.detail || payload.message || `Request failed (${response.status})`);
      error.status = response.status;
      error.code = isCloudflareChallenge(response,text) ? 'EDGE_CHALLENGE' : (isCsrfFailure(response,text) ? 'CSRF_ERROR' : 'API_ERROR');
      error.isEdgeChallenge = error.code === 'EDGE_CHALLENGE';
      error.isCsrfError = error.code === 'CSRF_ERROR';
      throw error;
    }
    return payload;
  }

  window.AlgoBotFrontendData = Object.freeze({request,list});
})();
