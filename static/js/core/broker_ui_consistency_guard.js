/* Canonical UI consistency guard.
 * The backend broker state is the only authority for connection/account display.
 * This prevents legacy widgets from showing a connected badge while the canonical
 * broker verification is degraded or unavailable.
 */
(() => {
  'use strict';
  if (window.__algoBotBrokerUIConsistencyGuard) return;
  window.__algoBotBrokerUIConsistencyGuard = true;

  const $ = selector => document.querySelector(selector);
  const safe = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const money = value => value == null || value === '' || Number.isNaN(Number(value)) ? 'Unavailable' : Number(value).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:8});

  function render(state) {
    if (!state) return;
    const account = state.account;
    const live = !!account && ['CONNECTED','SYNCING','READY'].includes(state.status);
    const indicator = $('[data-global-connection]');
    if (indicator) {
      const label = account?.broker?.name && account?.broker_account_id
        ? `${account.broker.name} · ${account.broker_account_id}`
        : state.status === 'DEGRADED' ? `Broker degraded${state.lastError ? ` · ${state.lastError}` : ''}`
        : state.status === 'ERROR' ? 'Broker connection error'
        : 'No connected broker account';
      indicator.classList.toggle('connected', live);
      indicator.classList.toggle('error', !live);
      indicator.innerHTML = `<i></i><span>${safe(label)}</span>`;
    }

    const card = $('[data-sidebar-account]');
    if (!card) return;
    if (!account) {
      card.innerHTML = `<span class="algobot-account-error">${safe(state.lastError || 'No connected broker account')}</span>`;
      return;
    }
    const broker = account.broker?.name || account.broker_name || 'Broker';
    const id = account.broker_account_id || account.account_id || 'Unknown account';
    const type = String(account.account_type || 'unknown').toUpperCase();
    const currency = account.currency || '';
    const detail = live ? `${type} · ${currency} ${money(account.balance)}` : `NOT LIVE · ${state.status}`;
    const freshness = live ? (account.last_synced_at ? `Verified ${new Date(account.last_synced_at).toLocaleTimeString()}` : 'Broker verified') : (state.lastError || 'Waiting for live broker verification');
    card.innerHTML = `<div class="algobot-account-summary"><span class="algobot-account-avatar small">${safe(broker[0]?.toUpperCase() || 'B')}</span><div class="algobot-account-copy"><strong>${safe(broker)} · ${safe(id)}</strong><span>${safe(detail)}</span></div></div><div class="algobot-account-fresh">${safe(freshness)}</div>`;
  }

  function boot() {
    const store = window.AlgoBotBrokerState;
    if (!store) return;
    store.subscribe(event => render(event.detail.state));
    render(store.get());
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true}); else boot();
})();
