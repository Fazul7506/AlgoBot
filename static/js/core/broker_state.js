/*
 * AlgoBot broker-backed frontend state contract.
 *
 * Backend/broker data is authoritative. This module is only the observable
 * browser state container shared by dashboard, terminal and other pages.
 */
(() => {
  'use strict';
  if (window.AlgoBotBrokerState) return;

  const STATES = Object.freeze({
    NO_BROKER: 'NO_BROKER', CONNECTING: 'CONNECTING', CONNECTED: 'CONNECTED',
    SYNCING: 'SYNCING', READY: 'READY', DEGRADED: 'DEGRADED',
    DISCONNECTED: 'DISCONNECTED', RECONNECTING: 'RECONNECTING', ERROR: 'ERROR'
  });

  const state = {
    status: STATES.NO_BROKER, connection: null, account: null, balances: null,
    positions: [], orders: [], trades: [], market: {}, strategies: [],
    automation: [], notifications: [], lastUpdatedAt: null, lastError: null
  };

  const listeners = new Set();
  const clone = value => {
    if (value == null) return value;
    if (typeof structuredClone === 'function') { try { return structuredClone(value); } catch (_) {} }
    return JSON.parse(JSON.stringify(value));
  };
  const snapshot = () => clone(state);

  function emit(reason) {
    state.lastUpdatedAt = new Date().toISOString();
    const detail = { reason, state: snapshot() };
    listeners.forEach(fn => { try { fn(detail); } catch (error) { setTimeout(() => { throw error; }, 0); } });
    window.dispatchEvent(new CustomEvent('algobot:state-changed', { detail }));
  }

  function transition(status, patch = {}, reason = 'transition') {
    if (!Object.values(STATES).includes(status)) throw new Error(`Invalid broker state: ${status}`);
    Object.assign(state, patch, { status, lastError: patch.lastError ?? (status === STATES.ERROR ? state.lastError : null) });
    emit(reason);
    return snapshot();
  }

  // Broker adapters have historically returned several equivalent connection
  // labels. Normalize them here so pages cannot disagree about READY vs offline.
  function accountIsConnected(account) {
    if (!account) return false;
    if (account.is_connected === true) return true;
    const value = String(account.status || account.connection_status || account.connection_state || '').trim().toLowerCase();
    return ['connected', 'ready', 'active', 'online', 'synchronized', 'syncing', 'degraded'].includes(value);
  }

  function setConnection(connection, reason = 'connection-updated') {
    if (!connection) return transition(STATES.NO_BROKER, { connection: null, account: null, balances: null }, reason);
    const connected = connection.is_connected === true || ['connected', 'ready', 'active', 'online'].includes(String(connection.status || '').toLowerCase());
    return transition(connected ? STATES.CONNECTED : STATES.DISCONNECTED, { connection }, reason);
  }

  function setAccount(account, reason = 'account-updated') {
    if (!account) return transition(STATES.NO_BROKER, { account: null, connection: null, balances: null }, reason);
    const connected = accountIsConnected(account);
    const raw = String(account.status || account.connection_status || '').trim().toLowerCase();
    const status = connected ? (raw === 'degraded' ? STATES.DEGRADED : raw === 'syncing' || raw === 'synchronized' ? STATES.SYNCING : STATES.READY) : STATES.DISCONNECTED;
    return transition(status, {
      account,
      balances: connected ? {
        balance: account.balance,
        equity: account.equity,
        margin: account.margin,
        available_margin: account.available_margin ?? account.free_margin,
        currency: account.currency
      } : null
    }, reason);
  }

  function patch(patch = {}, reason = 'state-patched') {
    const allowed = ['connection', 'account', 'balances', 'positions', 'orders', 'trades', 'market', 'strategies', 'automation', 'notifications', 'lastError'];
    allowed.forEach(key => { if (Object.prototype.hasOwnProperty.call(patch, key)) state[key] = clone(patch[key]); });
    if (patch.status) state.status = patch.status;
    emit(reason);
    return snapshot();
  }

  function subscribe(listener) {
    if (typeof listener !== 'function') return () => {};
    listeners.add(listener);
    listener({ reason: 'initial', state: snapshot() });
    return () => listeners.delete(listener);
  }

  function reset(reason = 'state-reset') {
    Object.assign(state, { status: STATES.NO_BROKER, connection: null, account: null, balances: null, positions: [], orders: [], trades: [], market: {}, strategies: [], automation: [], notifications: [], lastError: null });
    emit(reason);
    return snapshot();
  }

  window.AlgoBotBrokerState = Object.freeze({ STATES, get: snapshot, subscribe, transition, setConnection, setAccount, patch, reset, accountIsConnected });
})();
