/* AlgoBot frontend data contract: pages consume broker/backend state, never invent it. */
(() => {
  'use strict';
  if (window.AlgoBotFrontendData) return;

  const brokerState = () => window.AlgoBotBrokerState;
  const list = value => Array.isArray(value) ? value : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));
  const csrf = () => document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || '';

  async function request(url, options = {}, timeout = 12000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const headers = { Accept: 'application/json', ...(options.headers || {}) };
      if (options.method && !['GET', 'HEAD', 'OPTIONS'].includes(options.method.toUpperCase()) && !headers['X-CSRFToken']) headers['X-CSRFToken'] = csrf();
      const response = await fetch(url, { credentials: 'same-origin', ...options, headers, signal: controller.signal });
      const text = await response.text();
      let payload = {};
      try { payload = text ? JSON.parse(text) : {}; } catch (_) { payload = { detail: text }; }
      if (!response.ok) throw new Error(payload.detail || payload.message || `Request failed (${response.status})`);
      return payload;
    } catch (error) {
      if (error?.name === 'AbortError') throw new Error('Backend request timed out');
      throw error;
    } finally { clearTimeout(timer); }
  }

  async function getBrokerAccounts() {
    return list(await request('/api/brokers/accounts/'));
  }

  async function syncBrokerAccount(accountId) {
    if (!accountId) throw new Error('A broker account is required');
    if (brokerState()) brokerState().transition(brokerState().STATES.SYNCING, {}, 'account-sync-started');
    try {
      const result = await request(`/api/brokers/accounts/${encodeURIComponent(accountId)}/sync/`, { method: 'POST' });
      if (brokerState() && result.account) brokerState().setAccount(result.account, 'account-sync-complete');
      return result;
    } catch (error) {
      if (brokerState()) brokerState().transition(brokerState().STATES.ERROR, { lastError: error.message }, 'account-sync-failed');
      throw error;
    }
  }

  function requireConnected(action = 'perform this action') {
    const state = brokerState()?.get();
    if (!state?.account || state.status === brokerState().STATES.NO_BROKER || state.status === brokerState().STATES.DISCONNECTED) {
      const error = new Error(`Connect a broker before you ${action}.`);
      error.code = 'BROKER_NOT_CONNECTED';
      throw error;
    }
    return state;
  }

  function applyBrokerEvent(event = {}) {
    if (!brokerState()) return;
    const type = String(event.type || event.event || '').toLowerCase();
    const payload = event.data || event.payload || event;
    if (['broker_connected', 'connection.connected', 'connected'].includes(type)) return brokerState().transition(brokerState().STATES.CONNECTED, { connection: payload }, 'broker-event-connected');
    if (['broker_disconnected', 'connection.disconnected', 'disconnected'].includes(type)) return brokerState().transition(brokerState().STATES.DISCONNECTED, { connection: payload }, 'broker-event-disconnected');
    if (['account.updated', 'account_update', 'account'].includes(type)) return brokerState().setAccount(payload.account || payload, 'broker-event-account');
    if (['positions.updated', 'positions'].includes(type)) return brokerState().patch({ positions: list(payload.positions || payload) }, 'broker-event-positions');
    if (['orders.updated', 'orders'].includes(type)) return brokerState().patch({ orders: list(payload.orders || payload) }, 'broker-event-orders');
    if (['trades.updated', 'trades'].includes(type)) return brokerState().patch({ trades: list(payload.trades || payload) }, 'broker-event-trades');
    if (['market.updated', 'quote', 'market'].includes(type)) return brokerState().patch({ market: payload }, 'broker-event-market');
    return brokerState().patch({}, `broker-event:${type || 'unknown'}`);
  }

  window.AlgoBotFrontendData = Object.freeze({ request, getBrokerAccounts, syncBrokerAccount, requireConnected, applyBrokerEvent, list });
})();
