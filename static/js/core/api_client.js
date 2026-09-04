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
    if (bootstrappedCsrfToken) return bootstrappedCsrfToken;
    const cookieToken = readCookie('csrftoken');
    if (cookieToken) return decodeURIComponent(cookieToken);
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
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

  async function bootstrapCsrf() {
    const csrfUrl = new URL('/api/csrf/', apiBase || window.location.origin);
    const response = await nativeFetch(csrfUrl.toString(), { method: 'GET', credentials: 'include', headers: { Accept: 'application/json' }, cache: 'no-store' });
    if (!response.ok) return false;
    const payload = parsePayload(await response.clone().text());
    if (typeof payload.csrfToken === 'string' && payload.csrfToken) bootstrappedCsrfToken = payload.csrfToken;
    return Boolean(bootstrappedCsrfToken || csrfToken());
  }

  function normalizeOrderPayload(body) {
    if (typeof body !== 'string') return body;
    try {
      const payload = JSON.parse(body);
      if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return body;

      // The broker API model calls the foreign key `account`. Older terminal
      // code used `broker_account`, which DRF correctly rejected with HTTP 400.
      if (payload.account == null && payload.broker_account != null) payload.account = payload.broker_account;
      delete payload.broker_account;

      // ExecutionEngine consumes routing_context. Never send the frontend-only
      // validation_context key to OrderSerializer (it is not a model field).
      const routing = payload.routing_context && typeof payload.routing_context === 'object' ? {...payload.routing_context} : {};
      const validation = payload.validation_context && typeof payload.validation_context === 'object' ? payload.validation_context : {};
      Object.assign(routing, validation);
      Object.assign(routing, window.__algobotAiOrderContext || {});
      if (payload.account != null && routing.authoritative_account_id == null) routing.authoritative_account_id = payload.account;
      if (payload.symbol && routing.underlying_symbol == null) routing.underlying_symbol = payload.symbol;
      if (payload.contract_type && routing.contract_type == null) routing.contract_type = payload.contract_type;
      if (payload.contract_type == null && routing.contract_type) payload.contract_type = routing.contract_type;
      payload.routing_context = routing;
      delete payload.validation_context;
      return JSON.stringify(payload);
    } catch (_) {
      return body;
    }
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
      const apiOrigin = apiBase ? new URL(apiBase, window.location.origin).origin : window.location.origin;
      if (apiOrigin !== window.location.origin && !bootstrappedCsrfToken) {
        try { await bootstrapCsrf(); } catch (_) {}
      }
      const token = csrfToken();
      if (token && (!headers.has('X-CSRFToken') || !headers.get('X-CSRFToken'))) headers.set('X-CSRFToken', token);
    }

    const credentials = isProtected ? 'include' : (options.credentials || 'include');
    let requestInit = { ...options, method, headers, credentials };
    if (url.pathname === '/api/orders/' || url.pathname === '/api/orders/preview/') {
      requestInit.body = normalizeOrderPayload(requestInit.body);
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
          bootstrappedCsrfToken = '';
          try { await bootstrapCsrf(); } catch (_) {}
          const retryHeaders = new Headers(headers); retryHeaders.set('X-CSRFToken', csrfToken());
          return guardedFetch(input, { ...options, headers: retryHeaders }, false);
        }
      }
      return response;
    } catch (error) {
      if (controller.signal.aborted && !callerSignal?.aborted) { const timeout = new APIError(`API request timed out after ${timeoutMs}ms`, { code: 'API_TIMEOUT', url: url.toString(), method }); emitError(timeout); throw timeout; }
      if (callerSignal?.aborted) {
        const reason = callerSignal.reason;
        const message = reason?.message || 'Request was cancelled.';
        const cancelled = new APIError(message, { code: 'REQUEST_ABORTED', url: url.toString(), method });
        cancelled.retryable = false;
        throw cancelled;
      }
      const network = new APIError(error?.message || 'Network request failed', { code: 'NETWORK_ERROR', url: url.toString(), method }); emitError(network); throw network;
    } finally { clearTimeout(timer); }
  }

  class APIError extends Error {
    constructor(message, { status = 0, payload = {}, url = '', method = 'GET', response = null, code } = {}) {
      super(message); this.name = 'APIError'; this.status = status; this.payload = payload; this.url = url; this.method = method; this.response = response;
      this.code = code || payload?.code || (status ? `HTTP_${status}` : 'NETWORK_ERROR');
      this.retryable = status === 408 || status === 429 || status >= 500 || status === 0;
    }
  }

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
  window.fetch = guardedFetch;
  window.__algoBotApiClientFetch = true;
  window.AlgoBotAPI = Object.freeze({ APIClient, APIError, apiClient, csrfToken });
})();