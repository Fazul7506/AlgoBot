(() => {
  'use strict';
  if (window.__algoBotApiClientFetch) return;

  const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);
  const nativeFetch = window.fetch.bind(window);
  const configuredApiBase = (document.querySelector('meta[name="algobot-api-base"]')?.content || '').trim();
  const defaultApiBase = window.location.hostname === 'algobot.dpdns.org' || window.location.hostname === 'www.algobot.dpdns.org'
    ? 'https://api.algobot.dpdns.org'
    : '';
  const apiBase = (configuredApiBase || defaultApiBase).replace(/\/+$/, '');
  const aliases = {'/trading/order/': '/api/orders/', '/trading/preview/': '/api/orders/preview/', '/trading/ai/predict/': '/api/ai/predict/'};
  let bootstrappedCsrfToken = '';

  function readCookie(name) {
    const prefix = `${name}=`;
    const item = document.cookie.split(';').map(v => v.trim()).find(v => v.startsWith(prefix));
    return item ? item.slice(prefix.length) : '';
  }
  function csrfToken() {
    const cookieToken = readCookie('csrftoken');
    if (cookieToken) return decodeURIComponent(cookieToken);
    return document.querySelector('meta[name="csrf-token"]')?.content || bootstrappedCsrfToken || '';
  }
  function resolveUrl(path) {
    return new URL(aliases[path] || path || '/', apiBase || window.location.origin);
  }
  function protectedTarget(url) {
    const origins = new Set([window.location.origin]);
    if (apiBase) {
      try { origins.add(new URL(apiBase, window.location.origin).origin); } catch (_) {}
    }
    return origins.has(url.origin);
  }
  function parsePayload(text) { if (!text) return {}; try { return JSON.parse(text); } catch (_) { return { detail: text }; } }
  function messageFromPayload(payload, fallback) {
    if (!payload) return fallback;
    if (typeof payload === 'string') return payload;
    if (typeof payload.detail === 'string') return payload.detail;
    if (typeof payload.message === 'string') return payload.message;
    if (typeof payload.error === 'string') return payload.error;
    if (payload.detail && typeof payload.detail === 'object') return Object.entries(payload.detail).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`).join('; ');
    if (typeof payload === 'object') return Object.entries(payload).filter(([k]) => !['code', 'status'].includes(k)).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : typeof v === 'object' ? JSON.stringify(v) : v}`).join('; ') || fallback;
    return fallback;
  }
  function emitError(error) { window.dispatchEvent(new CustomEvent('algobot:api-error', { detail: { url: error.url, method: error.method, status: error.status, code: error.code, message: error.message, retryable: error.retryable } })); }

  class APIError extends Error {
    constructor(message, { status = 0, payload = {}, url = '', method = 'GET', response = null, code } = {}) {
      super(message); this.name = 'APIError'; this.status = status; this.payload = payload; this.url = url; this.method = method; this.response = response;
      this.code = code || payload?.code || (status ? `HTTP_${status}` : 'NETWORK_ERROR');
      this.retryable = status === 408 || status === 429 || status >= 500 || status === 0;
    }
  }

  async function bootstrapCsrf() {
    const csrfUrl = new URL('/api/csrf/', apiBase || window.location.origin);
    const response = await nativeFetch(csrfUrl.toString(), { method: 'GET', credentials: 'include', headers: { Accept: 'application/json' } });
    if (!response.ok) return false;
    const payload = parsePayload(await response.clone().text());
    if (typeof payload.csrfToken === 'string') bootstrappedCsrfToken = payload.csrfToken;
    return Boolean(csrfToken());
  }

  async function guardedFetch(input, init = {}, retryCsrf = true) {
    const options = init;
    const raw = typeof input === 'string' ? input : input?.url || '';
    const url = resolveUrl(raw);
    const method = String(options.method || (typeof input === 'object' && input?.method) || 'GET').toUpperCase();
    const headers = new Headers((typeof input === 'object' && input?.headers) || {});
    new Headers(options.headers || {}).forEach((value, key) => headers.set(key, value));
    headers.set('Accept', headers.get('Accept') || 'application/json');
    const isProtected = protectedTarget(url);

    if (!SAFE_METHODS.has(method) && isProtected) {
      if (!csrfToken()) await bootstrapCsrf();
      const token = csrfToken();
      if (token && !headers.has('X-CSRFToken')) headers.set('X-CSRFToken', token);
    }

    let requestInit = { ...options, method, headers, credentials: options.credentials || 'include' };
    if ((url.pathname === '/api/orders/' || url.pathname === '/api/orders/preview/') && typeof requestInit.body === 'string') {
      try { const payload = JSON.parse(requestInit.body); payload.validation_context = { ...(payload.validation_context || {}), ...(window.__algobotAiOrderContext || {}) }; requestInit.body = JSON.stringify(payload); } catch (_) {}
    }

    const controller = new AbortController();
    const callerSignal = options.signal;
    const timeoutMs = Number.isFinite(Number(options.__algoTimeoutMs)) ? Math.max(1000, Number(options.__algoTimeoutMs)) : 30000;
    const timer = setTimeout(() => controller.abort(new Error('API request timeout')), timeoutMs);
    const signal = callerSignal && typeof AbortSignal.any === 'function' ? AbortSignal.any([callerSignal, controller.signal]) : controller.signal;
    if (callerSignal?.aborted) controller.abort(callerSignal.reason);
    try {
      const response = await nativeFetch(url.toString(), { ...requestInit, signal });
      if (retryCsrf && response.status === 403 && !SAFE_METHODS.has(method) && isProtected) {
        const payload = parsePayload(await response.clone().text());
        if (payload?.code === 'CSRF_FAILED') {
          await bootstrapCsrf();
          const refreshedToken = csrfToken();
          if (refreshedToken) {
            const retryHeaders = new Headers(headers); retryHeaders.set('X-CSRFToken', refreshedToken);
            return guardedFetch(input, { ...options, headers: retryHeaders }, false);
          }
        }
      }
      return response;
    } catch (error) {
      if (controller.signal.aborted && !callerSignal?.aborted) { const timeout = new APIError(`API request timed out after ${timeoutMs}ms`, { code: 'API_TIMEOUT', url: url.toString(), method }); emitError(timeout); throw timeout; }
      const network = new APIError(error?.message || 'Network request failed', { code: 'NETWORK_ERROR', url: url.toString(), method }); emitError(network); throw network;
    } finally { clearTimeout(timer); }
  }

  window.fetch = guardedFetch;
  window.__algoBotApiClientFetch = true;

  class APIClient {
    constructor({ baseURL = apiBase, defaultHeaders = {}, timeout = 25000 } = {}) { this.baseURL = String(baseURL || '').replace(/\/+$/, ''); this.defaultHeaders = { Accept: 'application/json', ...defaultHeaders }; this.timeout = timeout; }
    buildUrl(path) { if (!path) return this.baseURL || '/'; if (/^https?:\/\//i.test(path)) return path; return `${this.baseURL}${path.startsWith('/') ? path : `/${path}`}`; }
    async request(path, options = {}) {
      const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), this.timeout);
      try {
        const response = await guardedFetch(this.buildUrl(path), { ...options, headers: { ...this.defaultHeaders, ...(options.headers || {}) }, signal: options.signal || controller.signal, __algoTimeoutMs: this.timeout });
        const payload = parsePayload(await response.text());
        if (!response.ok) { const error = new APIError(messageFromPayload(payload, `HTTP ${response.status} request failure`), { status: response.status, payload, url: response.url || this.buildUrl(path), method: options.method || 'GET', response }); emitError(error); throw error; }
        return payload;
      } finally { clearTimeout(timer); }
    }
    get(path, options = {}) { return this.request(path, { ...options, method: 'GET' }); }
    post(path, payload, options = {}) { return this.request(path, { ...options, method: 'POST', body: JSON.stringify(payload || {}), headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } }); }
    put(path, payload, options = {}) { return this.request(path, { ...options, method: 'PUT', body: JSON.stringify(payload || {}), headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } }); }
    patch(path, payload, options = {}) { return this.request(path, { ...options, method: 'PATCH', body: JSON.stringify(payload || {}), headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } }); }
    delete(path, options = {}) { return this.request(path, { ...options, method: 'DELETE' }); }
  }

  const apiClient = new APIClient();
  window.AlgoBotAPI = Object.freeze({ APIClient, APIError, apiClient, csrfToken });
})();
