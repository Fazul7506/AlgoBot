/* Runtime safety net for pages that depend on the shared frontend data contract. */
(() => {
  'use strict';
  if (window.AlgoBotFrontendData?.request) return;

  const list = value => Array.isArray(value)
    ? value
    : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));
  const csrf = () => document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || '';
  const edgeAlias = url => {
    try {
      const parsed = new URL(url, window.location.origin);
      if (parsed.origin !== window.location.origin || !parsed.pathname.startsWith('/api/')) return null;
      parsed.pathname = `/data/${parsed.pathname.slice('/api/'.length)}`;
      return `${parsed.pathname}${parsed.search}${parsed.hash}`;
    } catch (_) { return null; }
  };
  const isCloudflareChallenge = (response, text) => {
    const body = String(text || '').toLowerCase();
    const contentType = String(response?.headers?.get('content-type') || '').toLowerCase();
    return [403,429,503,520,521,522,524].includes(response?.status) &&
      (body.includes('just a moment') || body.includes('cf_chl_opt') || body.includes('challenge-platform') || body.includes('challenges.cloudflare.com') || body.includes('enable javascript and cookies to continue') || contentType.includes('text/html'));
  };
  const parse = (response, text) => {
    try { return text ? JSON.parse(text) : {}; }
    catch (_) { return {detail:isCloudflareChallenge(response,text) ? 'Production edge security challenged this API request.' : `Backend returned an unexpected response (${response?.status || 'unknown'}).`}; }
  };
  async function requestOnce(url, options, timeout) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), Math.max(1000, timeout));
    try {
      const method = String(options.method || 'GET').toUpperCase();
      const headers = {Accept:'application/json', ...(options.headers || {})};
      if (!['GET','HEAD','OPTIONS'].includes(method) && !headers['X-CSRFToken']) headers['X-CSRFToken'] = csrf();
      const response = await fetch(url,{credentials:'same-origin',...options,headers,signal:controller.signal});
      return {response,text:await response.text()};
    } finally { clearTimeout(timer); }
  }
  async function request(url, options = {}, timeout = 25000) {
    if (!url) throw new Error('No API endpoint configured');
    let result;
    try {
      const alias = edgeAlias(url);
      const primary = alias || url;
      result = await requestOnce(primary, options, timeout);
      if (primary !== url && !result.response.ok && (isCloudflareChallenge(result.response,result.text) || [404,405,502,503,504].includes(result.response.status))) result = await requestOnce(url, options, timeout);
    } catch (error) {
      if (error?.name === 'AbortError') throw new Error('Backend request timed out');
      throw error;
    }
    const {response,text} = result;
    const payload = parse(response,text);
    if (!response.ok) throw new Error(payload.detail || payload.message || `Request failed (${response.status})`);
    return payload;
  }
  window.AlgoBotFrontendData = Object.freeze({request,list});
})();
