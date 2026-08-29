/* AlgoBot frontend data contract: pages consume broker/backend state, never invent it. */
(() => {
  'use strict';
  if (window.AlgoBotFrontendData) return;
  const brokerState = () => window.AlgoBotBrokerState;
  const list = value => Array.isArray(value) ? value : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));
  const csrf = () => document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || document.querySelector('meta[name="csrf-token"]')?.content || '';
  const inflight = new Map();
  const cache = new Map();
  const GET_CACHE_MS = 1200;
  const configuredApiBase = (document.querySelector('meta[name="algobot-api-base"]')?.content || '').trim();
  const defaultApiBase = window.location.hostname === 'algobot.dpdns.org' ? 'https://api.algobot.dpdns.org' : '';
  const apiBase = (configuredApiBase || defaultApiBase).replace(/\/+$/, '');
  const resolveUrl = url => /^https?:\/\//i.test(url) ? url : `${apiBase}${url.startsWith('/') ? url : `/${url}`}`;
  const isCloudflareChallenge = (response, text) => {
    if (!response || !text) return false;
    const body = String(text).toLowerCase();
    return [400,403,429,503,520,521,522,524].includes(response.status) && (body.includes('just a moment') || body.includes('challenge-platform') || body.includes('cf_chl_opt') || body.includes('cf_chl-') || body.includes('challenges.cloudflare.com') || body.includes('enable javascript and cookies to continue') || (body.includes('cloudflare') && String(response.headers?.get('content-type') || '').toLowerCase().includes('text/html')));
  };
  const parsePayload = (response, text) => {
    try { return text ? JSON.parse(text) : {}; }
    catch (_) {
      if (isCloudflareChallenge(response, text)) return {detail:'Production API edge challenge encountered.', code:'EDGE_CHALLENGE'};
      const contentType = String(response?.headers?.get('content-type') || '').toLowerCase();
      return {detail:contentType.includes('text/html') ? `Backend returned an unexpected HTML response (${response.status}).` : String(text || `Request failed (${response?.status || 'unknown'})`)};
    }
  };
  async function fetchOnce(url, options, controller, sameOrigin = false) {
    const method = (options.method || 'GET').toUpperCase();
    const headers = {Accept:'application/json', ...(options.headers || {})};
    if (!['GET','HEAD','OPTIONS'].includes(method) && !headers['X-CSRFToken']) headers['X-CSRFToken'] = csrf();
    const target = sameOrigin ? url : resolveUrl(url);
    const crossOrigin = (() => { try { return new URL(target, window.location.origin).origin !== window.location.origin; } catch (_) { return false; } })();
    const response = await fetch(target, {credentials:crossOrigin ? 'include' : 'same-origin', ...options, headers, signal:controller.signal});
    return {response, text:await response.text()};
  }
  async function request(url, options = {}, timeout = 25000) {
    if (!url) throw new Error('No API endpoint configured');
    const method = (options.method || 'GET').toUpperCase();
    const key = `${method} ${url}`;
    if (method === 'GET') {
      if (inflight.has(key)) return inflight.get(key);
      const recent = cache.get(url);
      if (recent && Date.now() - recent.at <= GET_CACHE_MS) return recent.payload;
    }
    const promise = (async () => {
      let controller = new AbortController();
      let timer = setTimeout(() => controller.abort(), Math.max(1000, timeout));
      let result;
      let firstError = null;
      try {
        result = await fetchOnce(url, options, controller);
        if (isCloudflareChallenge(result.response, result.text) && apiBase && !/^https?:\/\//i.test(url)) {
          controller = new AbortController();
          clearTimeout(timer);
          timer = setTimeout(() => controller.abort(), Math.max(1000, timeout));
          try {
            const fallback = await fetchOnce(url, options, controller, true);
            if (!isCloudflareChallenge(fallback.response, fallback.text)) result = fallback;
          } catch (_) { /* retain edge response */ }
        }
      } catch (error) {
        firstError = error;
        // A timeout from the configured API host is not proof that the backend
        // is unavailable. Retry the same endpoint on the dashboard's origin so
        // deployments where the API subdomain is slow/unreachable can still
        // use the Django application directly.
        if (apiBase && !/^https?:\/\//i.test(url)) {
          try {
            controller = new AbortController();
            clearTimeout(timer);
            timer = setTimeout(() => controller.abort(), Math.max(1000, timeout));
            result = await fetchOnce(url, options, controller, true);
          } catch (fallbackError) {
            firstError = fallbackError;
            result = null;
          }
        }
        if (!result) {
          const e = new Error(firstError?.name === 'AbortError' ? 'Backend request timed out' : (firstError?.message || 'Network request failed'));
          e.code = firstError?.name === 'AbortError' ? 'API_TIMEOUT' : 'NETWORK_ERROR';
          e.status = 0;
          e.retryable = ['GET','HEAD'].includes(method);
          window.dispatchEvent(new CustomEvent('algobot:api-error', {detail:{url,method,status:0,code:e.code,message:e.message,retryable:e.retryable}}));
          throw e;
        }
      } finally { clearTimeout(timer); }
      const {response,text} = result;
      const payload = parsePayload(response,text);
      if (!response.ok) {
        const error = new Error(payload.detail || payload.message || `Request failed (${response.status})`);
        error.status = response.status;
        error.code = payload.code || (isCloudflareChallenge(response,text) ? 'EDGE_CHALLENGE' : 'API_ERROR');
        error.isEdgeChallenge = error.code === 'EDGE_CHALLENGE';
        error.retryable = ['GET','HEAD'].includes(method) && response.status >= 500;
        window.dispatchEvent(new CustomEvent('algobot:api-error', {detail:{url,method,status:response.status,code:error.code,message:error.message,retryable:error.retryable,edgeChallenge:error.isEdgeChallenge}}));
        throw error;
      }
      if (method === 'GET') cache.set(url,{payload,at:Date.now()});
      return payload;
    })();
    if (method === 'GET') inflight.set(key,promise);
    try { return await promise; } finally { if (inflight.get(key) === promise) inflight.delete(key); }
  }
  function cached(url,maxAge=120000) { const item=cache.get(url); return item && Date.now()-item.at<=maxAge ? item.payload : null; }
  async function getBrokerAccounts() { return list(await request('/api/brokers/accounts/')); }
  async function syncBrokerAccount(accountId) {
    if (!accountId) throw new Error('A broker account is required');
    if (typeof window.AlgoBotBrokerSync === 'function') return window.AlgoBotBrokerSync(accountId);
    if (brokerState()) brokerState().transition(brokerState().STATES.SYNCING,{},'account-sync-started');
    try { const result=await request(`/api/brokers/accounts/${encodeURIComponent(accountId)}/sync/`,{method:'POST'},25000); if (brokerState() && result.account) brokerState().setAccount(result.account,'account-sync-complete'); return result; }
    catch(error) { if (brokerState()) brokerState().transition(brokerState().STATES.ERROR,{lastError:error.message},'account-sync-failed'); throw error; }
  }
  function requireConnected(action='perform this action') { const state=brokerState()?.get(); if (!state?.account || state.status===brokerState().STATES.NO_BROKER || state.status===brokerState().STATES.DISCONNECTED) { const error=new Error(`Connect a broker before you ${action}.`); error.code='BROKER_NOT_CONNECTED'; throw error; } return state; }
  function applyBrokerEvent(event={}) {
    if (!brokerState()) return;
    const type=String(event.type || event.event || '').toLowerCase(); const payload=event.data || event.payload || event;
    if (['broker_connected','connection.connected','connected'].includes(type)) return brokerState().transition(brokerState().STATES.CONNECTED,{connection:payload},'broker-event-connected');
    if (['broker_disconnected','connection.disconnected','disconnected'].includes(type)) return brokerState().transition(brokerState().STATES.DISCONNECTED,{connection:payload},'broker-event-disconnected');
    if (['account.updated','account_update','account'].includes(type)) return brokerState().setAccount(payload.account || payload,'broker-event-account');
    if (['positions.updated','positions'].includes(type)) return brokerState().patch({positions:list(payload.positions || payload)},'broker-event-positions');
    if (['orders.updated','orders'].includes(type)) return brokerState().patch({orders:list(payload.orders || payload)},'broker-event-orders');
    if (['trades.updated','trades'].includes(type)) return brokerState().patch({trades:list(payload.trades || payload)},'broker-event-trades');
    if (['market.updated','quote','market'].includes(type)) return brokerState().patch({market:payload},'broker-event-market');
    return brokerState().patch({},`broker-event:${type || 'unknown'}`);
  }
  window.AlgoBotFrontendData = Object.freeze({request,cached,getBrokerAccounts,syncBrokerAccount,requireConnected,applyBrokerEvent,list});
})();