(() => {
  'use strict';
  if (window.__algoBotBrokerConnectionPage) return;
  window.__algoBotBrokerConnectionPage = true;

  const $ = selector => document.querySelector(selector);
  const labels = {
    NO_BROKER: ['No broker connected', 'Connect a broker to unlock broker-backed workspace data.', 'unknown'],
    CONNECTING: ['Connecting broker…', 'Authentication is in progress.', 'connecting'],
    CONNECTED: ['Broker connected', 'Broker connection established. Synchronizing account state.', 'connected'],
    SYNCING: ['Synchronizing broker…', 'Waiting for broker-confirmed account state.', 'syncing'],
    READY: ['Broker ready', 'Broker-confirmed account state is available.', 'ready'],
    DEGRADED: ['Broker connection degraded', 'The connection is available but broker data may be stale.', 'degraded'],
    DISCONNECTED: ['Broker disconnected', 'Reconnect before relying on live trading data.', 'disconnected'],
    RECONNECTING: ['Reconnecting broker…', 'Restoring broker connectivity.', 'connecting'],
    ERROR: ['Broker connection error', 'The broker connection could not be confirmed.', 'error']
  };

  function render(event) {
    const state = event?.detail?.state || window.AlgoBotBrokerState?.get();
    if (!state) return;
    const [title, message, kind] = labels[state.status] || labels.NO_BROKER;
    const badge = $('[data-connection-badge]');
    const account = $('[data-connection-account]');
    const copy = $('[data-connection-message]');
    if (badge) {
      badge.className = `ds-status ds-status--${kind}`;
      badge.textContent = title;
    }
    if (account) {
      const broker = state.account?.broker?.name;
      const accountId = state.account?.broker_account_id || state.account?.account_id;
      account.textContent = broker && accountId ? `${broker} · ${accountId}` : 'No broker account connected';
    }
    if (copy) copy.textContent = message;
  }

  function boot() {
    render();
    window.AlgoBotBrokerState?.subscribe(render);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
