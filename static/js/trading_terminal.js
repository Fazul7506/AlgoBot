/* Broker-backed trading terminal controller. */
(() => {
  'use strict';
  if (window.__algoBotTradingTerminal) return;
  window.__algoBotTradingTerminal = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
  const money = value => Number.isFinite(Number(value)) ? Number(value).toLocaleString(undefined, {maximumFractionDigits: 8}) : 'Unavailable';
  const api = (url, options, timeout) => window.AlgoBotFrontendData.request(url, options, timeout);
  let accounts = [];
  let direction = 'BUY';
  let loading = false;

  const connected = () => {
    const state = window.AlgoBotBrokerState?.get();
    return !!state?.account && ['CONNECTED', 'SYNCING', 'READY', 'DEGRADED'].includes(state.status);
  };

  function selectedAccount() {
    const id = $('#account')?.value;
    return accounts.find(account => String(account.id) === String(id)) || accounts.find(account => account.is_preferred || account.is_default) || accounts[0] || null;
  }

  function renderAccounts(nextAccounts) {
    accounts = list(nextAccounts).filter(account => account?.id);
    const select = $('#account');
    if (!select) return;
    const previous = select.value;
    if (!accounts.length) {
      select.innerHTML = '<option value="">No connected broker account</option>';
      return;
    }
    select.innerHTML = accounts.map(account => `<option value="${esc(account.id)}">${esc(account.broker?.name || account.broker_name || 'Broker')} · ${esc(account.broker_account_id || account.account_id)} · ${esc(account.currency || '')}</option>`).join('');
    const preferred = accounts.find(account => account.is_preferred || account.is_default);
    select.value = accounts.some(account => String(account.id) === previous) ? previous : String(preferred?.id || accounts[0].id);
    renderAccount(selectedAccount());
  }

  function renderAccount(account) {
    const status = $('#terminal-status');
    const note = $('[data-terminal-account]');
    if (!account) {
      if (status) status.textContent = 'Broker account required';
      if (note) note.textContent = 'No connected account';
      $('[data-risk-check]')?.replaceChildren(document.createTextNode('Connect broker first'));
      return;
    }
    if (status) status.textContent = `${account.broker?.name || account.broker_name || 'Broker'} account`;
    if (note) note.textContent = `Account: ${account.broker_account_id || account.account_id}`;
    $('[data-risk-check]')?.replaceChildren(document.createTextNode(account.is_connected ? 'Pre-trade checks active' : 'Broker verification required'));
  }

  async function loadSymbols() {
    const select = $('#symbol');
    if (!select) return '';
    const previous = select.value;
    try {
      const symbols = list(await api('/api/markets/symbols/')).filter(row => row?.symbol && row.is_active !== false && row.is_tradable !== false);
      if (!symbols.length) {
        select.innerHTML = '<option value="">No active broker instruments</option>';
        return '';
      }
      select.innerHTML = symbols.map(row => `<option value="${esc(row.symbol)}">${esc(row.display_name || row.symbol)} · ${esc(row.symbol)}</option>`).join('');
      const requested = new URLSearchParams(location.search).get('symbol');
      const chosen = [previous, requested, symbols[0].symbol].find(value => symbols.some(row => row.symbol === value));
      select.value = chosen;
      return chosen;
    } catch (error) {
      select.innerHTML = `<option value="">Market catalogue unavailable: ${esc(error.message)}</option>`;
      return '';
    }
  }

  async function loadQuote() {
    const symbol = $('#symbol')?.value;
    if (!symbol || !connected()) return;
    try {
      const tick = await api('/api/market/ticks/broker/', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({symbol})}, 9000);
      $('[data-q="bid"]')?.replaceChildren(document.createTextNode(money(tick.bid ?? tick.quote)));
      $('[data-q="ask"]')?.replaceChildren(document.createTextNode(money(tick.ask ?? tick.quote)));
    } catch (error) {
      $('[data-q="bid"]')?.replaceChildren(document.createTextNode('Quote unavailable'));
      $('[data-q="ask"]')?.replaceChildren(document.createTextNode('Quote unavailable'));
    }
  }

  const renderRows = (selector, rows, empty, format) => {
    const target = $(selector);
    if (target) target.innerHTML = rows.length ? rows.map(format).join('') : `<div class="empty-state">${esc(empty)}</div>`;
  };

  async function loadRecords() {
    if (!connected()) {
      renderRows('[data-positions]', [], 'Connect a broker to load positions.', () => '');
      renderRows('[data-orders]', [], 'Connect a broker to load orders.', () => '');
      return;
    }
    const [positions, orders] = await Promise.allSettled([api('/api/positions/open/'), api('/api/orders/')]);
    const positionRows = positions.status === 'fulfilled' ? list(positions.value) : [];
    const orderRows = orders.status === 'fulfilled' ? list(orders.value).slice(0, 8) : [];
    renderRows('[data-positions]', positionRows, positions.status === 'rejected' ? 'Positions are temporarily unavailable.' : 'No open positions.', row => `<div class="mini-row"><strong>${esc(row.symbol)}</strong><span>${esc(row.direction || row.side || '')}</span><b>${esc(row.profit ?? row.pnl ?? '—')}</b></div>`);
    renderRows('[data-orders]', orderRows, orders.status === 'rejected' ? 'Orders are temporarily unavailable.' : 'No orders yet.', row => `<div class="mini-row"><strong>${esc(row.symbol)}</strong><span>${esc(row.direction || '')}</span><b>${esc(row.status || '')}</b></div>`);
  }

  async function refresh() {
    if (loading) return;
    loading = true;
    try {
      const accountRows = window.AlgoBotBrokerAccounts?.length ? window.AlgoBotBrokerAccounts : await api('/api/brokers/accounts/');
      renderAccounts(accountRows);
      await loadSymbols();
      await Promise.all([loadQuote(), loadRecords()]);
    } finally { loading = false; }
  }

  async function submitOrder(event) {
    event.preventDefault();
    const account = selectedAccount();
    const symbol = $('#symbol')?.value;
    const result = $('[data-order-result]');
    if (!account || !symbol || !connected()) {
      if (result) { result.hidden = false; result.textContent = 'Connect and synchronize a broker account before placing an order.'; }
      return;
    }
    const form = new FormData(event.currentTarget);
    const button = $('.execute-btn');
    if (button) { button.disabled = true; button.textContent = 'Submitting…'; }
    try {
      const payload = {account:account.id, symbol, direction, order_type:form.get('order_type'), stake:form.get('stake'), strategy:form.get('strategy') || '', client_order_id:`ui-${crypto.randomUUID?.() || Date.now()}`, routing_context:window.__algobotAiOrderContext || {}};
      const order = await api('/api/orders/', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}, 25000);
      if (result) { result.hidden = false; result.textContent = `Order ${order.broker_order_id || order.id || ''} ${order.status || 'submitted'}.`; }
      window.__algobotAiOrderContext = null;
      await loadRecords();
    } catch (error) {
      if (result) { result.hidden = false; result.textContent = `Order rejected: ${error.message}`; }
    } finally { if (button) { button.disabled = false; button.textContent = 'Place order'; } }
  }

  function boot() {
    if (!$('.terminal-page')) return;
    $('[data-order-form]')?.addEventListener('submit', submitOrder);
    $('[data-action="terminal-refresh"]')?.addEventListener('click', refresh);
    $('#symbol')?.addEventListener('change', () => { loadQuote(); loadRecords(); });
    $('#account')?.addEventListener('change', () => renderAccount(selectedAccount()));
    document.querySelectorAll('[data-direction]').forEach(button => button.addEventListener('click', () => { direction = button.dataset.direction; document.querySelectorAll('[data-direction]').forEach(item => item.classList.toggle('active', item === button)); }));
    window.addEventListener('algobot:backend-accounts-loaded', event => renderAccounts(event.detail));
    window.addEventListener('algobot:account-synced', event => { renderAccounts((window.AlgoBotBrokerAccounts || accounts).map(account => String(account.id) === String(event.detail?.id) ? event.detail : account)); loadQuote(); });
    window.AlgoBotBrokerState?.subscribe(event => { if (['READY', 'CONNECTED', 'SYNCING'].includes(event.detail.state.status)) refresh(); else if (['NO_BROKER', 'DISCONNECTED'].includes(event.detail.state.status)) renderAccount(null); });
    refresh();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true}); else boot();
})();
