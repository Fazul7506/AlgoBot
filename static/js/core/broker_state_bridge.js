/* Canonical browser bridge for backend broker account state. */
(() => {
  'use strict';
  if (window.__algoBotBrokerStateBridge) return;
  window.__algoBotBrokerStateBridge = true;

  let lastAccountId = null;
  let lastConnection = null;
  let lastBalance = null;
  let busy = false;
  let timer = null;
  let syncTimer = null;

  const list = value => Array.isArray(value) ? value : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));

  async function requestJson(url, options = {}, timeoutMs = 10000) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json', ...(options.headers || {}) },
        cache: 'no-store',
        signal: controller.signal,
        ...options
      });
      let payload = null;
      try { payload = await response.json(); } catch (_) {}
      if (!response.ok) {
        const detail = payload?.detail || `Broker request failed (${response.status})`;
        const error = new Error(detail);
        error.status = response.status;
        error.payload = payload;
        throw error;
      }
      return payload;
    } finally { clearTimeout(timeout); }
  }

  async function refreshAccounts(store) {
    const accounts = list(await requestJson('/api/brokers/accounts/')).filter(account => account?.id);
    const account = accounts.find(item => item.is_default || item.is_preferred) || accounts[0] || null;
    if (!account) {
      if (lastAccountId !== null || lastConnection !== false) store.reset('backend-no-broker-account');
      lastAccountId = null; lastConnection = false; lastBalance = null;
      return null;
    }
    const connected = account.is_connected === true || store.accountIsConnected?.(account) === true;
    const id = String(account.id ?? account.broker_account_id ?? account.account_id ?? '');
    const balance = String(account.balance ?? '');
    if (id !== lastAccountId || connected !== lastConnection || balance !== lastBalance) store.setAccount(account, 'backend-broker-account-sync');
    lastAccountId = id; lastConnection = connected; lastBalance = balance;
    return account;
  }

  // A BrokerAccount row is not treated as proof that the remote broker session
  // works. Explicitly synchronize the preferred account through the backend,
  // which calls the real broker adapter and returns broker-authoritative data.
  async function verifyWithBroker(store, account) {
    if (!account?.id) return;
    store.transition(store.STATES.SYNCING, { account }, 'broker-verification-started');
    try {
      const payload = await requestJson(`/api/brokers/accounts/${encodeURIComponent(account.id)}/sync/`, { method: 'POST', headers: { 'Content-Type': 'application/json' } }, 10000);
      const verified = payload?.account || account;
      store.setAccount(verified, 'broker-verified-by-backend');
      window.dispatchEvent(new CustomEvent('algobot:account-synced', { detail: verified }));
    } catch (error) {
      const status = error.status;
      const brokerStatus = error.payload?.broker_status;
      if (status === 401 || brokerStatus === 'credentials_expired') store.transition(store.STATES.ERROR, { account, lastError: error.message }, 'broker-credentials-invalid');
      else if (status === 503 || brokerStatus === 'unavailable') store.transition(store.STATES.DEGRADED, { account, lastError: error.message }, 'broker-unavailable');
      else if (status === 504) store.transition(store.STATES.DEGRADED, { account, lastError: error.message }, 'broker-sync-timeout');
      else store.transition(store.STATES.ERROR, { account, lastError: error.message }, 'broker-sync-error');
      window.dispatchEvent(new CustomEvent('algobot:account-sync-error', { detail: { error, account } }));
    }
  }

  async function syncFromBackend() {
    const store = window.AlgoBotBrokerState;
    if (!store || document.body.dataset.authenticated !== 'true' || busy) return;
    busy = true;
    try {
      const account = await refreshAccounts(store);
      if (account && (account.is_connected !== true || !store.accountIsConnected?.(account))) {
        await verifyWithBroker(store, account);
      } else if (account) {
        // Even an apparently connected local row is periodically verified so
        // frontend state cannot silently drift from the actual broker session.
        await verifyWithBroker(store, account);
      }
    } catch (error) {
      if (!store.get().account) store.transition(store.STATES.ERROR, { lastError: error.message }, 'backend-broker-account-error');
    } finally { busy = false; }
  }

  function schedule() {
    if (timer) clearInterval(timer);
    if (syncTimer) clearInterval(syncTimer);
    syncFromBackend();
    setTimeout(syncFromBackend, 1000);
    timer = setInterval(syncFromBackend, 30000);
  }

  window.addEventListener('algobot:account-changed', event => {
    if (window.AlgoBotBrokerState && event.detail) window.AlgoBotBrokerState.setAccount(event.detail, 'account-changed');
    lastAccountId = String(event.detail?.id ?? event.detail?.broker_account_id ?? '');
    lastConnection = event.detail?.is_connected === true;
    lastBalance = String(event.detail?.balance ?? '');
  });
  window.addEventListener('algobot:account-synced', event => {
    if (window.AlgoBotBrokerState && event.detail) window.AlgoBotBrokerState.setAccount(event.detail, 'account-synced');
    lastAccountId = String(event.detail?.id ?? event.detail?.broker_account_id ?? '');
    lastConnection = event.detail?.is_connected === true;
    lastBalance = String(event.detail?.balance ?? '');
  });
  window.addEventListener('algobot:account-sync-error', event => {
    if (window.AlgoBotBrokerState && !window.AlgoBotBrokerState.get().account) window.AlgoBotBrokerState.transition(window.AlgoBotBrokerState.STATES.ERROR, {lastError:event.detail?.error?.message || 'Broker account synchronization failed'}, 'account-sync-error');
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', schedule, {once:true});
  else schedule();
})();
