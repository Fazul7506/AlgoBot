/* Sidebar broker-account switcher.
 * Uses the same authoritative selection contract as the trading terminal.
 * The backend remains the authority for eligibility and active-account state.
 */
(() => {
  'use strict';
  if (window.__algoBotSidebarAccountSwitch) return;
  window.__algoBotSidebarAccountSwitch = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || (Array.isArray(value) ? value : (Array.isArray(value?.results) ? value.results : []));
  const safe = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const money = value => value == null || value === '' || Number.isNaN(Number(value)) ? 'Unavailable' : Number(value).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:8});
  const typeOf = account => String(account?.account_type || account?.credentials?.account_type || 'demo').toLowerCase();
  let accounts = [];
  let switching = false;

  const api = (url, options = {}, timeout = 15000) => {
    if (window.AlgoBotFrontendData?.request) return window.AlgoBotFrontendData.request(url, options, timeout);
    return Promise.reject(new Error('Broker API client is not ready.'));
  };

  function activeAccount() {
    const stateAccount = window.AlgoBotBrokerState?.get?.().account;
    if (stateAccount?.id) return accounts.find(a => String(a.id) === String(stateAccount.id)) || stateAccount;
    return accounts.find(a => a.is_active === true) || accounts.find(a => a.is_default || a.is_preferred) || accounts[0] || null;
  }

  function targetFor(current) {
    if (!current) return null;
    const brokerId = current.broker?.id ?? current.broker_id;
    const opposite = accounts.find(a => String(a.id) !== String(current.id) && typeOf(a) !== typeOf(current) && (brokerId == null || String(a.broker?.id ?? a.broker_id) === String(brokerId)));
    return opposite || accounts.find(a => String(a.id) !== String(current.id) && typeOf(a) !== typeOf(current)) || null;
  }

  function render() {
    const card = $('[data-sidebar-account]');
    if (!card) return;
    const current = activeAccount();
    const target = targetFor(current);
    if (!current) {
      card.innerHTML = '<span class="algobot-account-error">No connected broker account</span>';
      return;
    }
    const broker = current.broker?.name || current.broker_name || 'Broker';
    const id = current.broker_account_id || current.account_id || current.id;
    const type = typeOf(current).toUpperCase();
    const targetType = target ? typeOf(target).toUpperCase() : '';
    const targetId = target ? (target.broker_account_id || target.account_id || target.id) : '';
    const state = window.AlgoBotBrokerState?.get?.() || {};
    const live = current.is_connected === true || ['CONNECTED','READY','SYNCING'].includes(state.status);
    const switchTitle = target ? `Switch to ${targetType} account ${targetId}` : 'No alternate broker account is available';
    const disabled = !target || switching;
    card.classList.add('algobot-account-modal-trigger');
    card.setAttribute('role', 'group');
    card.removeAttribute('tabindex');
    card.removeAttribute('aria-label');
    card.innerHTML = `<div class="algobot-account-summary"><span class="algobot-account-avatar small">${safe(broker[0]?.toUpperCase() || 'B')}</span><div class="algobot-account-copy"><strong>${safe(broker)} · ${safe(id)}</strong><span>${safe(type)} · ${safe(current.currency || '')} ${safe(money(current.balance))}</span></div></div><div class="algobot-account-fresh">${safe(live ? (current.last_synced_at ? `Verified ${new Date(current.last_synced_at).toLocaleTimeString()}` : 'Broker verified') : `Account ${current.status || 'unavailable'}`)}</div><button type="button" class="algobot-account-switch" data-account-switch ${disabled ? 'disabled' : ''} title="${safe(switchTitle)}" aria-label="${safe(target ? `Switch to ${targetType} account ${targetId}` : 'No alternate broker account available')}">${target ? `<span class="algobot-switch-avatar">${safe(target.broker?.name?.[0]?.toUpperCase() || broker[0]?.toUpperCase() || 'B')}</span><span>Switch to ${safe(targetType)}</span>` : '<span>Demo / Real</span>'}</button>`;
  }

  async function refreshAccounts() {
    try {
      accounts = list(await api('/api/brokers/accounts/', {notifyOnError:false}, 9000)).filter(a => a?.id);
      window.AlgoBotBrokerAccounts = accounts.slice();
      render();
    } catch (_) {
      const canonical = window.AlgoBotBrokerAccounts;
      if (Array.isArray(canonical) && canonical.length) accounts = canonical.filter(a => a?.id);
      render();
    }
  }

  async function selectAccount(id) {
    if (switching || !id) return;
    const target = accounts.find(a => String(a.id) === String(id));
    if (!target) return;
    switching = true;
    render();
    try {
      const accountType = ['demo','real'].includes(typeOf(target)) ? typeOf(target) : '';
      const options = {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(accountType ? {account_type: accountType} : {}),
        notifyOnError: true,
      };
      const response = await api(`/api/brokers/accounts/${encodeURIComponent(id)}/select/`, options, 15000);
      let selected = response?.active_account || response?.account;
      if (!selected?.id) throw new Error('Broker did not confirm the selected account.');
      try {
        const authoritative = await api('/api/brokers/accounts/active/', {notifyOnError:false}, 9000);
        selected = authoritative?.active_account || selected;
      } catch (_) {}
      accounts = accounts.map(a => String(a.id) === String(selected.id) ? selected : {...a, is_active:false, is_preferred:false});
      window.AlgoBotBrokerAccounts = accounts.slice();
      if (window.AlgoBotBrokerState?.setAccount) window.AlgoBotBrokerState.setAccount(selected, 'sidebar-account-switch');
      window.dispatchEvent(new CustomEvent('algobot:account-changed', {detail:selected}));
      render();
    } catch (error) {
      render();
      window.AlgoBotMessage?.(error?.message || 'Account switch failed.', 'error');
    } finally {
      switching = false;
      render();
    }
  }

  function bind() {
    const card = $('[data-sidebar-account]');
    if (!card || card.dataset.accountSwitchBound === 'true') return;
    card.dataset.accountSwitchBound = 'true';
    card.addEventListener('click', event => {
      const button = event.target?.closest?.('[data-account-switch]');
      if (!button || button.disabled) return;
      event.preventDefault();
      event.stopPropagation();
      const current = activeAccount();
      const target = targetFor(current);
      void selectAccount(target?.id);
    }, true);
  }

  function boot() {
    if (document.body.dataset.authenticated !== 'true') return;
    bind();
    refreshAccounts();
    window.addEventListener('algobot:backend-accounts-loaded', event => {
      accounts = list(event.detail).filter(a => a?.id);
      render();
    });
    window.addEventListener('algobot:account-changed', event => {
      if (event.detail?.id) accounts = accounts.map(a => String(a.id) === String(event.detail.id) ? event.detail : {...a, is_active:false, is_preferred:false});
      render();
    });
    window.addEventListener('algobot:account-synced', event => {
      if (event.detail?.id) accounts = accounts.map(a => String(a.id) === String(event.detail.id) ? event.detail : a);
      render();
    });
    window.addEventListener('algobot:state-changed', () => render());
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true});
  else boot();
})();
