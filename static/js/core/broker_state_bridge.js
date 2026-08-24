/* Bridges the existing live_broker_ui into the canonical broker state contract. */
(() => {
  'use strict';
  if (window.__algoBotBrokerStateBridge) return;
  window.__algoBotBrokerStateBridge = true;

  let lastAccountId = null;
  let lastConnection = null;

  function sync() {
    const store = window.AlgoBotBrokerState;
    const ui = window.AlgoBotBrokerUI;
    if (!store || !ui?.getCurrentAccount) return;
    const account = ui.getCurrentAccount();
    if (!account) {
      if (lastAccountId !== null || lastConnection !== false) store.reset('live-ui-no-account');
      lastAccountId = null;
      lastConnection = false;
      return;
    }
    const connected = account.is_connected === true;
    const id = String(account.id ?? account.broker_account_id ?? account.account_id ?? '');
    if (id !== lastAccountId || connected !== lastConnection) {
      store.setAccount(account, 'live-ui-account-sync');
      lastAccountId = id;
      lastConnection = connected;
    }
  }

  window.addEventListener('algobot:account-changed', event => {
    if (window.AlgoBotBrokerState && event.detail) window.AlgoBotBrokerState.setAccount(event.detail, 'account-changed');
    lastAccountId = String(event.detail?.id ?? '');
    lastConnection = event.detail?.is_connected === true;
  });
  window.addEventListener('algobot:account-synced', event => {
    if (window.AlgoBotBrokerState && event.detail) window.AlgoBotBrokerState.setAccount(event.detail, 'account-synced');
    lastAccountId = String(event.detail?.id ?? '');
    lastConnection = event.detail?.is_connected === true;
  });
  window.addEventListener('algobot:account-sync-error', event => {
    if (window.AlgoBotBrokerState) window.AlgoBotBrokerState.transition(window.AlgoBotBrokerState.STATES.ERROR, { lastError: event.detail?.error?.message || 'Broker account synchronization failed' }, 'account-sync-error');
  });

  function boot() {
    sync();
    setTimeout(sync, 250);
    setTimeout(sync, 1000);
    setInterval(sync, 5000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
