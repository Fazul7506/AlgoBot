/* Canonical broker-account selector for the trading terminal. */
(() => {
  'use strict';
  if (window.__algoBotAccountSwitchFix) return;
  window.__algoBotAccountSwitchFix = true;

  const $ = (s, r = document) => r.querySelector(s);
  const list = value => Array.isArray(value) ? value : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));
  const csrf = () => document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || '';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));

  async function request(url, options = {}, timeout = 10000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const headers = {Accept:'application/json', ...(options.headers || {})};
      if (options.method && options.method !== 'GET') headers['X-CSRFToken'] = csrf();
      const response = await fetch(url, {credentials:'same-origin', ...options, headers, signal:controller.signal});
      const raw = await response.text();
      let data = {};
      try { data = raw ? JSON.parse(raw) : {}; } catch (_) { data = {detail: raw}; }
      if (!response.ok) throw new Error(data.detail || data.message || `Request failed (${response.status})`);
      return data;
    } finally { clearTimeout(timer); }
  }

  const accountType = a => String(a?.account_type || a?.credentials?.account_type || '').toLowerCase();
  const idOf = a => a?.id ?? a?.pk;
  const labelOf = a => `${a?.broker?.name || a?.broker_name || 'Broker'} · ${a?.broker_account_id || a?.account_id || 'Account'} · ${accountType(a).toUpperCase() || 'UNKNOWN'}`;

  let accounts = [];
  let switching = false;

  function publish(account, reason) {
    if (!account) return;
    window.AlgoBotBrokerState?.setAccount?.(account, reason || 'account-switched');
    window.AlgoBotBrokerState?.patch?.({account}, reason || 'account-switched');
    window.dispatchEvent(new CustomEvent('algobot:account-changed', {detail: account}));
    window.dispatchEvent(new CustomEvent('algobot:account-synced', {detail: account}));
  }

  function renderSelect(selectedId) {
    const select = $('#account');
    if (!select) return;
    const currentId = selectedId != null ? String(selectedId) : String(select.value || '');
    select.innerHTML = accounts.length
      ? accounts.map(a => `<option value="${esc(idOf(a))}">${esc(labelOf(a))}</option>`).join('')
      : '<option value="">No connected broker accounts</option>';
    const preferred = accounts.find(a => a.is_preferred || a.is_default);
    const selected = accounts.find(a => String(idOf(a)) === currentId) || preferred || accounts[0];
    if (selected) select.value = String(idOf(selected));
    select.disabled = accounts.length < 1 || switching;
    select.setAttribute('aria-label', 'Select active broker account');
  }

  function updateSidebar(account) {
    const card = $('[data-sidebar-account]');
    if (!card || !account) return;
    const type = accountType(account).toUpperCase();
    const name = account.broker?.name || account.broker_name || 'Broker';
    const accountId = account.broker_account_id || account.account_id || '';
    const currency = account.currency || '';
    const balance = account.balance == null ? '—' : Number(account.balance).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:8});
    card.querySelector('.algobot-account-summary')?.replaceChildren();
    const summary = document.createElement('div');
    summary.className = 'algobot-account-summary';
    summary.innerHTML = `<div class="algobot-account-copy"><strong>${esc(name)} · ${esc(accountId)}</strong><span>${esc(type)} · ${esc(currency)} ${esc(balance)}</span></div>`;
    card.innerHTML = '';
    card.appendChild(summary);
    const fresh = document.createElement('div');
    fresh.className = 'algobot-account-fresh';
    fresh.textContent = account.last_synced_at ? `Synced ${new Date(account.last_synced_at).toLocaleTimeString()}` : 'Last known broker data';
    card.appendChild(fresh);
  }

  async function switchAccount(id) {
    if (switching) return;
    const account = accounts.find(a => String(idOf(a)) === String(id));
    if (!account || account.is_preferred) return;
    if (account.switch_enabled === false) throw new Error('Broker account switching is disabled.');
    switching = true;
    renderSelect(id);
    try {
      const type = accountType(account);
      if (!['demo','real'].includes(type)) throw new Error('Broker has not confirmed whether this account is DEMO or REAL. Synchronize it first.');
      if (account.status && account.status !== 'active') throw new Error('The selected broker account is not active.');
      if (account.is_connected === false) throw new Error('The selected broker account is not connected.');
      const result = await request(`/api/brokers/accounts/${encodeURIComponent(idOf(account))}/select/`, {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({account_type:type})
      }, 10000);
      const active = result.active_account || result.account;
      if (!active) throw new Error('Broker did not return the newly active account.');
      accounts = accounts.map(a => String(idOf(a)) === String(idOf(active)) ? active : {...a, is_preferred:false, is_default:false});
      publish(active, 'account-switch-confirmed');
      updateSidebar(active);
      renderSelect(idOf(active));
      window.AlgoBotBrokerUI?.updateTerminalAccount?.(active);
    } catch (error) {
      const preferred = accounts.find(a => a.is_preferred || a.is_default);
      renderSelect(idOf(preferred));
      window.AlgoBotMessage?.(error?.message || 'Broker account switch failed.', 'error');
    } finally {
      switching = false;
      renderSelect($('#account')?.value);
    }
  }

  async function load() {
    try {
      const payload = await request('/api/brokers/accounts/', {}, 10000);
      accounts = list(payload).filter(a => idOf(a) != null);
      window.AlgoBotBrokerAccounts = accounts;
      const preferred = accounts.find(a => a.is_preferred || a.is_default) || accounts[0] || null;
      renderSelect(idOf(preferred));
      if (preferred) {
        publish(preferred, 'canonical-accounts-loaded');
        updateSidebar(preferred);
        window.AlgoBotBrokerUI?.updateTerminalAccount?.(preferred);
      }
    } catch (error) {
      window.AlgoBotMessage?.(error?.message || 'Unable to load broker accounts.', 'error');
    }
  }

  function boot() {
    if (!$('.terminal-page')) return;
    const select = $('#account');
    if (select && !select.dataset.accountSwitchFixBound) {
      select.dataset.accountSwitchFixBound = '1';
      // Capture phase prevents legacy terminal code from treating a switch as
      // a sync-only operation. The server select action is the source of truth.
      select.addEventListener('change', event => {
        event.stopImmediatePropagation();
        switchAccount(select.value);
      }, true);
    }
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true});
  else boot();
})();
