/* Runtime safety net for pages that depend on the shared frontend data contract. */
(() => {
  'use strict';
  if (window.AlgoBotFrontendData?.request) return;

  const list = value => Array.isArray(value)
    ? value
    : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));

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

  const parse = (response, text) => {
    try { return text ? JSON.parse(text) : {}; }
    catch (_) { return {detail:isCloudflareChallenge(response,text) ? 'Production edge security challenged this API request.' : `Backend returned an unexpected response (${response?.status || 'unknown'}).`}; }
  };

  async function requestOnce(url, options, timeout, sameOrigin = false) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), Math.max(1000, timeout));
    try {
      const headers = {Accept:'application/json', ...(options.headers || {})};
      const target = sameOrigin ? url : resolveUrl(url);
      const crossOrigin = (() => { try { return new URL(target, window.location.origin).origin !== window.location.origin; } catch (_) { return false; } })();
      const response = await fetch(target,{credentials:crossOrigin ? 'include' : 'same-origin',...options,headers,signal:controller.signal});
      return {response,text:await response.text()};
    } finally { clearTimeout(timer); }
  }

  async function request(url, options = {}, timeout = 25000) {
    if (!url) throw new Error('No API endpoint configured');
    let result = await requestOnce(url, options, timeout);
    const method = String(options.method || 'GET').toUpperCase();
    if (isCloudflareChallenge(result.response, result.text) && apiBase && !/^https?:\/\//i.test(url) && ['GET','HEAD','OPTIONS'].includes(method)) {
      try {
        const fallback = await requestOnce(url, options, timeout, true);
        if (!isCloudflareChallenge(fallback.response, fallback.text)) result = fallback;
      } catch (_) {}
    }
    const {response,text} = result;
    const payload = parse(response,text);
    if (!response.ok) {
      const error = new Error(payload.detail || payload.message || `Request failed (${response.status})`);
      error.status = response.status;
      error.code = isCloudflareChallenge(response,text) ? 'EDGE_CHALLENGE' : 'API_ERROR';
      error.isEdgeChallenge = error.code === 'EDGE_CHALLENGE';
      throw error;
    }
    return payload;
  }

  window.AlgoBotFrontendData = Object.freeze({request,list});
})();
