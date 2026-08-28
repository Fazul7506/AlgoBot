/* AlgoBot frontend data contract: pages consume broker/backend state, never invent it. */
(() => {
  'use strict';
  if (window.AlgoBotFrontendData) return;
  const brokerState = () => window.AlgoBotBrokerState;
  const list = value => Array.isArray(value) ? value : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));
  const csrf = () => document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || '';
  const inflight = new Map();
  const cache = new Map();
  const GET_CACHE_MS = 1200;
  const cloudflareAlias = url => typeof url === 'string' && url.startsWith('/api/') ? `/data/${url.slice(5)}` : null;
  const isCloudflareChallenge = (response, text) => {
    if (!response || !text) return false;
    const body = String(text).toLowerCase();
    return [403,429,503,520,521,522,524].includes(response.status) && (body.includes('just a moment') || body.includes('challenge-platform') || body.includes('cf_chl_opt') || body.includes('cf-chl-') || body.includes('enable javascript and cookies to continue'));
  };
  const parsePayload = (response, text) => {
    try { return text ? JSON.parse(text) : {}; }
    catch (_) {
      if (isCloudflareChallenge(response, text)) return {detail:'Production edge security challenged this API request.', code:'EDGE_CHALLENGE'};
      const contentType = String(response?.headers?.get('content-type') || '').toLowerCase();
      return {detail:contentType.includes('text/html') ? `Backend returned an unexpected HTML response (${response.status}).` : String(text || `Request failed (${response?.status || 'unknown'})`)};
    }
  };
  async function fetchOnce(url, options, controller) {
    const method = (options.method || 'GET').toUpperCase();
    const headers = {Accept:'application/json', ...(options.headers || {})};
    if (!['GET','HEAD','OPTIONS'].includes(method) && !headers['X-CSRFToken']) headers['X-CSRFToken'] = csrf();
    const response = await fetch(url, {credentials:'same-origin', ...options, headers, signal:controller.signal});
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
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), Math.max(1000, timeout));
    const promise = (async () => {
      try {
        const alias = cloudflareAlias(url);
        const primary = alias || url;
        let result = await fetchOnce(primary, options, controller);
        if (primary !== url && !result.response.ok && !isCloudflareChallenge(result.response, result.text) && [404,405,502,503,504].includes(result.response.status)) {
          result = await fetchOnce(url, options, controller);
        }
        const {response, text} = result;
        const payload = parsePayload(response, text);
        if (!response.ok) {
          const error = new Error(payload.detail || payload.message || `Request failed (${response.status})`);
          error.status = response.status;
          error.code = payload.code || error.code;
          error.isEdgeChallenge = error.code === 'EDGE_CHALLENGE';
          window.dispatchEvent(new CustomEvent('algobot:api-error', {detail:{url, method, status:response.status, code:error.code || 'API_ERROR', message:error.message, retryable:['GET','HEAD'].includes(method), edgeChallenge:error.isEdgeChallenge}}));
          throw error;
        }
        if (method === 'GET') cache.set(url,{payload,at:Date.now()});
        return payload;
      } catch (error) {
        if (error?.name === 'AbortError' || error?.name === 'AlgoBotTimeoutError') {
          const e=new Error('Backend request timed out');
          e.code='API_TIMEOUT';
          window.dispatchEvent(new CustomEvent('algobot:api-error', {detail:{url, method, status:0, code:e.code, message:e.message, retryable:['GET','HEAD'].includes(method)}}));
          throw e;
        }
        if (error?.code === 'EDGE_CHALLENGE' || error?.code === 'API_ERROR') throw error;
        window.dispatchEvent(new CustomEvent('algobot:api-error', {detail:{url, method, status:error?.status || 0, code:error?.code || 'NETWORK_ERROR', message:error?.message || 'Network request failed', retryable:['GET','HEAD'].includes(method)}}));
        throw error;
      } finally { clearTimeout(timer); }
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
