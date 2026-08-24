/* Canonical browser bridge for backend broker account state. */
(() => {
  'use strict';
  if (window.__algoBotBrokerStateBridge) return;
  window.__algoBotBrokerStateBridge = true;

  let lastAccountId = null;
  let lastConnection = null;
  let busy = false;

  const list = value => Array.isArray(value)
    ? value
    : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));

  async function syncFromBackend() {
    const store = window.AlgoBotBrokerState;
    if (!store || document.body.dataset.authenticated !== 'true' || busy) return;
    busy = true;
    try {
      const response = await fetch('/api/brokers/accounts/', {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
        cache: 'no-store'
      });
      if (!response.ok) throw new Error(`Broker account request failed (${response.status})`);
      const accounts = list(await response.json()).filter(account => account?.id);
      const account = accounts.find(item => item.is_default || item.is_preferred) || accounts[0] || null;
      if (!account) {
        if (lastAccountId !== null || lastConnection !== false) store.reset('backend-no-broker-account');
        lastAccountId = null;
        lastConnection = false;
        return;
      }
      const connected = account.is_connected === true || account.status === 'active';
      const id = String(account.id ?? account.broker_account_id ?? account.account_id ?? '');
      if (id !== lastAccountId || connected !== lastConnection || store.get().account?.balance !== account.balance) {
        store.setAccount(account, 'backend-broker-account-sync');
      }
      lastAccountId = id;
      lastConnection = connected;
    } catch (error) {
      /* Do not erase a known-good broker state because one poll failed. */
      if (!store.get().account) {
        store.transition(store.STATES.ERROR, { lastError: error.message }, 'backend-broker-account-error');
      }
    } finally {
      busy = false;
    }
  }

  window.addEventListener('algobot:account-changed', event => {
    if (window.AlgoBotBrokerState && event.detail) window.AlgoBotBrokerState.setAccount(event.detail, 'account-changed');
    lastAccountId = String(event.detail?.id ?? event.detail?.broker_account_id ?? '');
    lastConnection = event.detail?.is_connected === true || event.detail?.status === 'active';
  });
  window.addEventListener('algobot:account-synced', event => {
    if (window.AlgoBotBrokerState && event.detail) window.AlgoBotBrokerState.setAccount(event.detail, 'account-synced');
    lastAccountId = String(event.detail?.id ?? event.detail?.broker_account_id ?? '');
    lastConnection = event.detail?.is_connected === true || event.detail?.status === 'active';
  });
  window.addEventListener('algobot:account-sync-error', event => {
    if (window.AlgoBotBrokerState && !window.AlgoBotBrokerState.get().account) {
      window.AlgoBotBrokerState.transition(window.AlgoBotBrokerState.STATES.ERROR, { lastError: event.detail?.error?.message || 'Broker account synchronization failed' }, 'account-sync-error');
    }
  });

  function boot() {
    syncFromBackend();
    setTimeout(syncFromBackend, 500);
    setInterval(syncFromBackend, 5000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
