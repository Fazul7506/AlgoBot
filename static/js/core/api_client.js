(() => {
  'use strict';
  if (window.__algoBotApiClientFetch) return;

  const nativeFetch = window.fetch.bind(window);
  const configuredApiBase = (document.querySelector('meta[name="algobot-api-base"]')?.content || '').trim();
  const productionApiBase = ['algobot.dpdns.org', 'www.algobot.dpdns.org'].includes(window.location.hostname)
    ? 'https://api.algobot.dpdns.org'
    : '';
  // Production browser API traffic must never fall back to the web/page origin.
  const apiBase = (configuredApiBase || productionApiBase || window.location.origin).replace(/\/+$/, '');
  const aliases = {'/trading/order/': '/api/orders/', '/trading/preview/': '/api/orders/preview/', '/trading/ai/predict/': '/api/ai/predict/'};

  function resolveUrl(path) {
    const raw = String(aliases[path] || path || '/');
    if (/^https?:\/\//i.test(raw)) {
      const absolute = new URL(raw, window.location.origin);
      if (productionApiBase && ['algobot.dpdns.org', 'www.algobot.dpdns.org'].includes(absolute.hostname)) {
        return new URL(`${absolute.pathname}${absolute.search}${absolute.hash}`, productionApiBase);
      }
      return absolute;
    }
    return new URL(raw, `${apiBase}/`);
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

  function normalizeOrderPayload(body) {
    if (typeof body !== 'string') return body;
    try {
      const payload = JSON.parse(body);
      if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return body;
      const routing = payload.routing_context && typeof payload.routing_context === 'object' ? {...payload.routing_context} : {};
      const validation = payload.validation_context && typeof payload.validation_context === 'object' ? payload.validation_context : {};
      Object.assign(routing, validation);
      Object.assign(routing, window.__algobotAiOrderContext || {});
      const selectedId = window.AlgoBotAccountContext?.getSelectedId?.() || window.AlgoBotBrokerState?.get?.()?.account?.id;
      if (selectedId != null && routing.authoritative_account_id == null) routing.authoritative_account_id = selectedId;
      if (payload.broker_account != null && routing.authoritative_account_id == null) routing.authoritative_account_id = payload.broker_account;
      if (payload.symbol && routing.underlying_symbol == null) routing.underlying_symbol = payload.symbol;
      if (payload.contract_type && routing.contract_type == null) routing.contract_type = payload.contract_type;
      if (payload.contract_type == null && routing.contract_type) payload.contract_type = routing.contract_type;
      payload.routing_context = routing;
      delete payload.validation_context;
      return JSON.stringify(payload);
    } catch (_) { return body; }
  }

  async function guardedFetch(input, init = {}) {
    const options = init;
    const raw = typeof input === 'string' ? input : input?.url || '';
    const url = resolveUrl(raw);
    const method = String(options.method || (typeof input === 'object' && input?.method) || 'GET').toUpperCase();
    const headers = new Headers((typeof input === 'object' && input?.headers) || {});
    new Headers(options.headers || {}).forEach((value, key) => headers.set(key, value));
    headers.set('Accept', headers.get('Accept') || 'application/json');
    const selectedId = window.AlgoBotAccountContext?.getSelectedId?.() || window.AlgoBotBrokerState?.get?.()?.account?.id;
    if (selectedId != null && !headers.has('X-Algobot-Account-ID')) headers.set('X-Algobot-Account-ID', String(selectedId));
    let body = options.body;
    if (url.pathname === '/api/orders/' || url.pathname === '/api/orders/preview/') body = normalizeOrderPayload(body);
    const controller = new AbortController();
    const callerSignal = options.signal;
    const timeoutMs = Number.isFinite(Number(options.__algoTimeoutMs)) ? Math.max(1000, Number(options.__algoTimeoutMs)) : 30000;
    const timer = setTimeout(() => controller.abort(new Error('API request timeout')), timeoutMs);
    const signal = callerSignal && typeof AbortSignal.any === 'function' ? AbortSignal.any([callerSignal, controller.signal]) : controller.signal;
    if (callerSignal?.aborted) controller.abort(callerSignal.reason);
    try {
      try {
        return await nativeFetch(url.toString(), {...options, method, body, headers, credentials: options.credentials || 'include', signal});
      } catch (error) {
        if (controller.signal.aborted && !callerSignal?.aborted) {
          const timeout = new APIError('API request timed out after ' + timeoutMs + 'ms', {code:'API_TIMEOUT',url:url.toString(),method});
          emitError(timeout); throw timeout;
        }
        if (callerSignal?.aborted) {
          const cancelled = new APIError(callerSignal.reason?.message || 'Request was cancelled.', {code:'REQUEST_ABORTED',url:url.toString(),method});
          cancelled.retryable = false; throw cancelled;
        }
        const network = new APIError(error?.message || 'Network request failed', {code:'NETWORK_ERROR',url:url.toString(),method});
        emitError(network); throw network;
      }
    } finally { clearTimeout(timer); }
  }

  class APIError extends Error {
    constructor(message, {status=0,payload={},url='',method='GET',response=null,code}={}) { super(message); this.name='APIError'; this.status=status; this.payload=payload; this.url=url; this.method=method; this.response=response; this.code=code||payload?.code||(status?`HTTP_${status}`:'NETWORK_ERROR'); this.retryable=status===408||status===429||status>=500||status===0; }
  }

  class APIClient {
    constructor({baseURL=apiBase,defaultHeaders={},timeout=25000}={}) { this.baseURL=String(baseURL||'').replace(/\/+$/,''); this.defaultHeaders={Accept:'application/json',...defaultHeaders}; this.timeout=timeout; }
    buildUrl(path) { return resolveUrl(path).toString(); }
    async request(path, options={}) {
      const response = await guardedFetch(this.buildUrl(path), {...options, headers:{...this.defaultHeaders,...(options.headers||{})}, __algoTimeoutMs:options.__algoTimeoutMs||this.timeout});
      const payload = parsePayload(await response.text());
      if (!response.ok) { const error = new APIError(messageFromPayload(payload, `HTTP ${response.status} request failure`), {status:response.status,payload,url:response.url||this.buildUrl(path),method:options.method||'GET',response}); emitError(error); throw error; }
      return payload;
    }
    get(path, options={}) { return this.request(path,{...options,method:'GET'}); }
    post(path,payload,options={}) { return this.request(path,{...options,method:'POST',body:JSON.stringify(payload||{}),headers:{'Content-Type':'application/json',...(options.headers||{})}}); }
    put(path,payload,options={}) { return this.request(path,{...options,method:'PUT',body:JSON.stringify(payload||{}),headers:{'Content-Type':'application/json',...(options.headers||{})}}); }
    patch(path,payload,options={}) { return this.request(path,{...options,method:'PATCH',body:JSON.stringify(payload||{}),headers:{'Content-Type':'application/json',...(options.headers||{})}}); }
    delete(path,options={}) { return this.request(path,{...options,method:'DELETE'}); }
  }

  const apiClient = new APIClient();
  window.__algoBotApiClientFetch = true;
  window.AlgoBotAPI = Object.freeze({APIClient,APIError,apiClient,apiBase});
})();
