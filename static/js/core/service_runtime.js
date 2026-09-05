/* AlgoBot Unified Service Runtime. Cross-service browser infrastructure lives here. */
(() => {
  'use strict';
  if (window.AlgoBotServiceRuntime) return;

  const active = new Map();
  const controllers = new Map();
  const registry = new Map();
  const errors = [];
  const recentErrorKeys = new Map();
  const MAX_ERRORS = 100;
  const now = () => new Date().toISOString();
  const accountId = () => String(window.AlgoBotAccountContext?.getSelectedId?.() || window.AlgoBotBrokerState?.get?.()?.account?.id || '');
  const emit = (name, detail = {}) => window.dispatchEvent(new CustomEvent(name, {detail:{...detail, at:now(), accountId:accountId()}}));
  const inferService = url => {
    const path = String(url || '').toLowerCase();
    if (path.includes('/ai/') || path.includes('/predict')) return 'ai';
    if (path.includes('data-center') || path.includes('/market')) return 'market-data';
    if (path.includes('/orders')) return 'orders';
    if (path.includes('/positions')) return 'positions';
    if (path.includes('/strateg')) return 'strategies';
    if (path.includes('/risk')) return 'risk';
    if (path.includes('/monitor')) return 'monitoring';
    if (path.includes('/notification')) return 'notifications';
    if (path.includes('/automation')) return 'automation';
    if (path.includes('/portfolio')) return 'portfolio';
    if (path.includes('/backtest')) return 'backtesting';
    return document.body?.dataset.service || 'platform';
  };
  const register = (name, config = {}) => {
    if (!name) throw new Error('A service name is required.');
    const value = {...(registry.get(name) || {}), ...config, name, registeredAt:(registry.get(name) || {}).registeredAt || now()};
    registry.set(name, value);
    emit('algobot:service-registered', {service:value});
    return Object.freeze({...value});
  };
  const begin = (name, label = 'Loading…') => {
    active.set(name, (active.get(name) || 0) + 1);
    document.documentElement.dataset.algobotBusy = 'true';
    emit('algobot:service-loading', {service:name, label, count:active.get(name)});
    return () => end(name);
  };
  const end = name => {
    const count = Math.max(0, (active.get(name) || 0) - 1);
    count ? active.set(name, count) : active.delete(name);
    if (!active.size) delete document.documentElement.dataset.algobotBusy;
    emit('algobot:service-idle', {service:name, count});
  };
  const retryable = error => Boolean(error && (error.retryable ?? ['NETWORK_ERROR','API_TIMEOUT','SERVICE_TIMEOUT'].includes(error.code) || Number(error.status) >= 500));
  async function withTimeout(task, timeout = 25000, name = 'service') {
    const key = `${name}:${Date.now()}:${Math.random()}`;
    const controller = new AbortController();
    controllers.set(key, controller);
    let timer;
    try {
      return await Promise.race([
        Promise.resolve().then(() => task({signal:controller.signal})),
        new Promise((_, reject) => { timer = setTimeout(() => { controller.abort(); const error = new Error(`${name} timed out after ${timeout}ms.`); error.code='SERVICE_TIMEOUT'; error.service=name; error.retryable=true; reject(error); }, Math.max(1000, timeout)); })
      ]);
    } finally { clearTimeout(timer); controllers.delete(key); }
  }
  async function run(name, task, {timeout=25000, retry=0, retryDelay=1000, label='Loading…'} = {}) {
    const release = begin(name, label);
    try {
      for (let attempt=0; attempt<=retry; attempt++) {
        try { return await withTimeout(task, timeout, name); }
        catch (error) { if (attempt>=retry || !retryable(error)) throw error; await new Promise(resolve => setTimeout(resolve, retryDelay * (attempt+1))); }
      }
    } finally { release(); }
  }
  const cancel = name => { for (const [key, controller] of controllers) if (key.startsWith(`${name}:`)) controller.abort(); emit('algobot:service-cancelled', {service:name}); };
  const recordError = detail => {
    const entry = {
      at:now(), service:detail.service || inferService(detail.url), url:detail.url || '', method:detail.method || 'GET',
      status:Number(detail.status || 0), code:detail.code || 'UNKNOWN_ERROR', message:detail.message || 'Request failed.',
      accountId:accountId(), retryable:Boolean(detail.retryable)
    };
    const dedupeKey = `${entry.service}|${entry.url}|${entry.method}|${entry.status}|${entry.code}|${entry.accountId}|${entry.message}`;
    const last = recentErrorKeys.get(dedupeKey) || 0;
    if (Date.now() - last < 750) return errors[errors.length - 1] || entry;
    recentErrorKeys.set(dedupeKey, Date.now());
    if (recentErrorKeys.size > 250) for (const [key, stamp] of recentErrorKeys) if (Date.now() - stamp > 10000) recentErrorKeys.delete(key);
    errors.push(entry);
    if (errors.length > MAX_ERRORS) errors.shift();
    emit('algobot:service-error', {error:entry});
    return entry;
  };
  const request = async (name, url, options = {}, timeout = 25000) => {
    const service = name || inferService(url);
    const headers = new Headers(options.headers || {});
    const id = accountId();
    headers.set('Accept', headers.get('Accept') || 'application/json');
    if (id && !headers.has('X-Algobot-Account-ID')) headers.set('X-Algobot-Account-ID', id);
    try {
      const response = await withTimeout(({signal}) => fetch(url, {credentials:'same-origin', cache:'no-store', ...options, headers, signal}), timeout, service);
      const text = await response.text();
      let payload = {};
      try { payload = text ? JSON.parse(text) : {}; } catch (_) { payload = {detail:text}; }
      if (!response.ok) {
        const error = Object.assign(new Error(payload?.detail || payload?.message || `${service} request failed (${response.status}).`), {status:response.status, payload, code:`HTTP_${response.status}`, retryable:response.status>=500 || response.status===429});
        recordError({service,url,method:options.method||'GET',status:error.status,code:error.code,message:error.message,retryable:error.retryable});
        throw error;
      }
      return payload;
    } catch (error) {
      if (error?.code !== 'SERVICE_TIMEOUT' && !error?.code?.startsWith?.('HTTP_')) recordError({service,url,method:options.method||'GET',status:error?.status||0,code:error?.code||'NETWORK_ERROR',message:error?.message||'Network request failed.',retryable:true});
      throw error;
    }
  };
  const snapshot = () => ({accountId:accountId(), services:[...registry.values()].map(value => ({...value})), loading:Object.fromEntries(active), errors:errors.slice(-20)});
  window.AlgoBotServiceRuntime = Object.freeze({register,begin,end,run,withTimeout,request,cancel,isRetryable:retryable,recordError,recentErrors:n => errors.slice(-Math.max(1,n||20)),snapshot,accountId});
  window.addEventListener('algobot:api-error', event => {
    const detail = event.detail || {};
    const entry = recordError(detail);
    window.dispatchEvent(new CustomEvent('algobot:recoverable-error', {detail:entry}));
  });
  const reset = () => { active.clear(); delete document.documentElement.dataset.algobotBusy; emit('algobot:services-account-reset'); };
  window.addEventListener('algobot:account-changed', reset);
  window.addEventListener('algobot:account-context-changed', reset);
  window.addEventListener('algobot:recoverable-error', event => {
    const detail = event.detail || {};
    document.querySelectorAll('[data-global-error]').forEach(element => { element.textContent = detail.message || 'The service is temporarily unavailable. Please try again.'; element.hidden = false; });
    document.querySelectorAll('[data-service-retry]').forEach(element => { element.hidden = !detail.retryable; element.dataset.retryService = detail.service || ''; });
  });

  // Compatibility boundary: legacy page scripts may still call fetch directly, but
  // same-origin calls inherit account context and centralized error classification.
  const featureFetch = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : input?.url || '';
    const headers = new Headers((typeof input === 'object' && input?.headers) || {});
    new Headers(init.headers || {}).forEach((value, key) => headers.set(key, value));
    const id = accountId();
    try {
      const target = new URL(url, window.location.origin);
      if (target.origin === window.location.origin && id && !headers.has('X-Algobot-Account-ID')) headers.set('X-Algobot-Account-ID', id);
      const response = await featureFetch(input, {...init, headers});
      if (!response.ok) recordError({service:inferService(url),url,method:init.method||'GET',status:response.status,code:`HTTP_${response.status}`,message:`${inferService(url)} request failed (${response.status}).`,retryable:response.status>=500 || response.status===429});
      return response;
    } catch (error) {
      if (!['API_TIMEOUT','REQUEST_ABORTED'].includes(error?.code)) recordError({service:inferService(url),url,method:init.method||'GET',status:error?.status||0,code:error?.code||'NETWORK_ERROR',message:error?.message||'Network request failed.',retryable:true});
      throw error;
    }
  };
  emit('algobot:service-runtime-ready', {version:4});
})();
