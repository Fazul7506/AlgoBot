(() => {
  'use strict';
  if (window.__algoBotApiClientFetch) return;

  const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);
  const nativeFetch = window.fetch.bind(window);
  const apiBase = document.querySelector('meta[name="algobot-api-base"]')?.content || '';
  const aliases = {
    '/trading/order/': '/api/orders/',
    '/trading/preview/': '/api/orders/preview/',
    '/trading/ai/predict/': '/api/ai/predict/',
  };

  function readCookie(name) {
    const prefix = `${name}=`;
    const item = document.cookie.split(';').map(v => v.trim()).find(v => v.startsWith(prefix));
    return item ? item.slice(prefix.length) : '';
  }

  function csrfToken() {
    const cookieToken = readCookie('csrftoken');
    if (cookieToken) return decodeURIComponent(cookieToken);
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
  }

  function resolveUrl(path) {
    const raw = aliases[path] || path || '/';
    return new URL(raw, apiBase || window.location.origin);
  }

  function isProtectedTarget(url) {
    const allowed = new Set([window.location.origin]);
    if (apiBase) {
      try { allowed.add(new URL(apiBase, window.location.origin).origin); } catch (_) {}
    }
    return allowed.has(url.origin);
  }

  function messageFromPayload(payload, fallback) {
    if (!payload) return fallback;
    if (typeof payload === 'string') return payload;
    if (typeof payload.detail === 'string') return payload.detail;
    if (typeof payload.message === 'string') return payload.message;
    if (typeof payload.error === 'string') return payload.error;
    if (payload.detail && typeof payload.detail === 'object') return Object.entries(payload.detail).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`).join('; ');
    if (typeof payload === 'object') {
      const entries = Object.entries(payload).filter(([k]) => k !== 'code' && k !== 'status');
      if (entries.length) return entries.map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : typeof v === 'object' ? JSON.stringify(v) : v}`).join('; ');
    }
    return fallback;
  }

  async function parseResponse(response) {
    const text = await response.text();
    if (!text) return {};
    try { return JSON.parse(text); } catch (_) { return { detail: text }; }
  }

  class APIError extends Error {
    constructor(message, { status = 0, payload = {}, url = '', method = 'GET', response = null } = {}) {
      super(message);
      this.name = 'APIError';
      this.status = status;
      this.payload = payload;
      this.url = url;
      this.method = method;
      this.response = response;
      this.code = payload?.code || (status ? `HTTP_${status}` : 'NETWORK_ERROR');
      this.retryable = status === 408 || status === 429 || status >= 500 || status === 0;
    }
  }

  async function ensureCsrfCookie() {
    if (csrfToken()) return true;
    const response = await nativeFetch('/api/csrf/', { method: 'GET', credentials: 'same-origin', headers: { Accept: 'application/json' } });
    return response.ok && Boolean(csrfToken());
  }

  async function perform(input, init, retryCsrf = true) {
    let url = resolveUrl(typeof input === 'string' ? input : input?.url || '');
    let requestInit = { ...init };
    const method = String(requestInit.method || (typeof input === 'object' && input?.method) || 'GET').toUpperCase();
    const protectedTarget = isProtectedTarget(url);
    const headers = new Headers((typeof input === 'object' && input?.headers) || {});
    new Headers(requestInit.headers || {}).forEach((value, key) => headers.set(key, value));
    headers.set('Accept', headers.get('Accept') || 'application/json');

    if (!SAFE_METHODS.has(method) && protectedTarget) {
      if (!csrfToken()) await ensureCsrfCookie();
      const token = csrfToken();
      if (token && !headers.has('X-CSRFToken')) headers.set('X-CSRFToken', token);
    }

    if ((url.pathname === '/api/orders/' || url.pathname === '/api/orders/preview/') && typeof requestInit.body === 'string') {
      try {
        const payload = JSON.parse(requestInit.body);
        payload.validation_context = { ...(payload.validation_context || {}), ...(window.__algobotAiOrderContext || {}) };
        requestInit.body = JSON.stringify(payload);
      } catch (_) {}
    }

    requestInit = {
      ...requestInit,
      method,
      headers,
      credentials: requestInit.credentials || (protectedTarget ? 'include' : 'same-origin'),
    };

    const response = await nativeFetch(url.toString(), requestInit);
    const payload = await parseResponse(response);
    if (response.ok) return payload;

    const error = new APIError(messageFromPayload(payload, `Request failed (${response.status})`), {
      status: response.status,
      payload,
      url: url.toString(),
      method,
      response,
    });

    if (retryCsrf && response.status === 403 && payload?.code === 'CSRF_FAILED' && !SAFE_METHODS.has(method) && protectedTarget) {
      await ensureCsrfCookie();
      return perform(input, { ...init, headers: { ...Object.fromEntries(headers.entries()), 'X-CSRFToken': csrfToken() } }, false);
    }
    throw error;
  }

  window.fetch = (input, init = {}) => perform(input, init);
  window.__algoBotApiClientFetch = true;

  class APIClient {
    constructor({ baseURL = apiBase, defaultHeaders = {}, timeout = 25000 } = {}) {
      this.baseURL = String(baseURL || '').replace(/\/+$/, '');
      this.defaultHeaders = { Accept: 'application/json', ...defaultHeaders };
      this.timeout = timeout;
    }

    buildUrl(path) {
      if (!path) return this.baseURL || '/';
      if (/^https?:\/\//i.test(path)) return path;
      return `${this.baseURL}${path.startsWith('/') ? path : `/${path}`}`;
    }

    async request(path, options = {}) {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(new Error('API request timeout')), this.timeout);
      try {
        return await window.fetch(this.buildUrl(path), {
          ...options,
          headers: { ...this.defaultHeaders, ...(options.headers || {}) },
          signal: options.signal || controller.signal,
        });
      } catch (error) {
        if (error?.name === 'AbortError') throw new APIError(`API request timed out after ${this.timeout}ms`, { code: 'API_TIMEOUT' });
        throw error;
      } finally {
        clearTimeout(timeoutId);
      }
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
