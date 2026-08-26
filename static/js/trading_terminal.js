/* Reliable broker-backed trading terminal. */
(() => {
  'use strict';
  if (window.__algoBotTradingTerminal) return;
  window.__algoBotTradingTerminal = true;

  const $ = (s, r = document) => r.querySelector(s);
  const list = v => window.AlgoBotFrontendData?.list(v) || [];
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const money = v => Number.isFinite(Number(v)) ? Number(v).toLocaleString(undefined, {maximumFractionDigits: 8}) : 'Unavailable';
  const api = (url, options = {}, timeout = 10000) => window.AlgoBotFrontendData.request(url, options, timeout);
  let accounts = [], direction = 'BUY', busy = false;

  const selectedAccount = () => {
    const id = $('#account')?.value;
    return accounts.find(a => String(a.id) === String(id)) || accounts.find(a => a.is_preferred || a.is_default) || accounts[0] || null;
  };
  const brokerReady = () => !!selectedAccount();

  const renderRows = (selector, rows, empty, format) => {
    const target = $(selector);
    if (target) target.innerHTML = rows.length ? rows.map(format).join('') : `<div class="empty-state">${esc(empty)}</div>`;
  };

  function renderAccount(account) {
    const status = $('#terminal-status'), note = $('[data-terminal-account]'), risk = $('[data-risk-check]');
    if (!account) {
      if (status) status.textContent = 'Broker account required';
      if (note) note.textContent = 'No connected account';
      if (risk) risk.textContent = 'Connect broker first';
      return;
    }
    const broker = account.broker?.name || account.broker_name || 'Broker';
    if (status) status.textContent = `${broker} account`;
    if (note) note.textContent = `Account: ${account.broker_account_id || account.account_id}`;
    if (risk) risk.textContent = account.is_connected === false ? 'Broker verification required' : 'Pre-trade checks active';
  }

  function renderAccounts(rows) {
    accounts = list(rows).filter(a => a?.id);
    const select = $('#account');
    if (!select) return;
    const previous = select.value;
    if (!accounts.length) {
      select.innerHTML = '<option value="">No connected broker account</option>';
      renderAccount(null);
      return;
    }
    select.innerHTML = accounts.map(a => `<option value="${esc(a.id)}">${esc(a.broker?.name || a.broker_name || 'Broker')} · ${esc(a.broker_account_id || a.account_id)} · ${esc(a.currency || '')}</option>`).join('');
    const preferred = accounts.find(a => a.is_preferred || a.is_default);
    select.value = accounts.some(a => String(a.id) === previous) ? previous : String(preferred?.id || accounts[0].id);
    renderAccount(selectedAccount());
  }

  async function loadAccounts() {
    try {
      const rows = window.AlgoBotBrokerAccounts?.length ? window.AlgoBotBrokerAccounts : await api('/api/brokers/accounts/', {}, 9000);
      renderAccounts(rows);
      return selectedAccount();
    } catch (e) {
      renderAccounts([]);
      $('[data-terminal-account]')?.replaceChildren(document.createTextNode(`Broker accounts unavailable: ${e.message || 'request failed'}`));
      return null;
    }
  }

  async function loadSymbols() {
    const select = $('#symbol'); if (!select) return '';
    const previous = select.value;
    try {
      // Use the terminal-specific authenticated catalogue: it contains only
      // active/tradable instruments and avoids the much larger public symbol
      // endpoint during page boot.
      const payload = await api('/api/market/catalogue/', {}, 15000);
      const symbols = list(payload?.symbols ?? payload).filter(r => r?.symbol && r.is_active !== false && r.is_tradable !== false);
      if (!symbols.length) throw new Error('No active tradable broker instruments are available');
      select.innerHTML = symbols.map(r => `<option value="${esc(r.symbol)}">${esc(r.display_name || r.symbol)} · ${esc(r.symbol)}</option>`).join('');
      const requested = new URLSearchParams(location.search).get('symbol');
      select.value = [previous, requested, symbols[0].symbol].find(v => symbols.some(r => r.symbol === v)) || symbols[0].symbol;
      return select.value;
    } catch (e) {
      select.innerHTML = `<option value="">${esc(e.message || 'Market catalogue unavailable')}</option>`;
      return '';
    }
  }

  async function loadQuote() {
    const symbol = $('#symbol')?.value;
    if (!symbol || !brokerReady()) return;
    const bid = $('[data-q="bid"]'), ask = $('[data-q="ask"]');
    try {
      const tick = await api(`/api/market/ticks/broker/?symbol=${encodeURIComponent(symbol)}`, {}, 9000);
      const bidValue = tick.bid ?? tick.quote, askValue = tick.ask ?? tick.quote;
      if (bid) bid.textContent = money(bidValue);
      if (ask) ask.textContent = money(askValue);
      $('[data-chart-loading]')?.replaceChildren(document.createTextNode(tick.stale ? 'Last known broker quote · reconnecting live feed' : 'Live broker quote received'));
    } catch (e) {
      try {
        const cached = await api(`/api/ticks/latest/?symbol=${encodeURIComponent(symbol)}`, {}, 5000);
        if (cached?.quote != null) {
          if (bid) bid.textContent = money(cached.bid ?? cached.quote);
          if (ask) ask.textContent = money(cached.ask ?? cached.quote);
          $('[data-chart-loading]')?.replaceChildren(document.createTextNode('Last known quote · live broker reconnecting'));
          return;
        }
      } catch (_) {}
      if (bid) bid.textContent = 'Unavailable';
      if (ask) ask.textContent = 'Unavailable';
      $('[data-chart-loading]')?.replaceChildren(document.createTextNode(`Broker quote unavailable: ${e.message || 'request failed'}`));
    }
  }

  async function loadRecords() {
    if (!brokerReady()) {
      renderRows('[data-positions]', [], 'Connect a broker to load positions.', () => '');
      renderRows('[data-orders]', [], 'Connect a broker to load orders.', () => '');
      return;
    }
    const [positions, orders] = await Promise.allSettled([api('/api/positions/open/', {}, 9000), api('/api/orders/?limit=8', {}, 9000)]);
    const p = positions.status === 'fulfilled' ? list(positions.value) : [];
    const o = orders.status === 'fulfilled' ? list(orders.value).slice(0, 8) : [];
    renderRows('[data-positions]', p, positions.status === 'rejected' ? 'Positions temporarily unavailable.' : 'No open positions.', r => `<div class="mini-row"><strong>${esc(r.symbol || '—')}</strong><span>${esc(r.direction || r.side || '')}</span><b>${esc(r.profit ?? r.pnl ?? '—')}</b></div>`);
    renderRows('[data-orders]', o, orders.status === 'rejected' ? 'Orders temporarily unavailable.' : 'No orders yet.', r => `<div class="mini-row"><strong>${esc(r.symbol || '—')}</strong><span>${esc(r.direction || r.side || '')}</span><b>${esc(r.status || '')}</b></div>`);
  }

  async function loadSignals() {
    const target = $('[data-signals]'); if (!target) return;
    try {
      const data = await api('/api/dashboard/signals/?limit=8', {}, 8000);
      const rows = list(data);
      target.innerHTML = rows.length ? rows.map(r => `<div class="mini-row"><strong>${esc(r.symbol || 'Signal')}</strong><span>${esc(r.direction || r.signal || r.action || '')}</span><b>${esc(r.confidence ?? r.status ?? '')}</b></div>`).join('') : '<div class="empty-state">No active strategy signals.</div>';
    } catch (e) { target.innerHTML = `<div class="empty-state">Signals temporarily unavailable.</div>`; }
  }

  async function refresh() {
    if (busy) return; busy = true;
    try {
      await loadAccounts();
      const symbol = await loadSymbols();
      await Promise.all([loadQuote(), loadRecords(), loadSignals()]);
      if (symbol) $('#symbol')?.dispatchEvent(new Event('change', {bubbles: true}));
    } finally { busy = false; }
  }

  async function submitOrder(event) {
    event.preventDefault();
    const account = selectedAccount(), symbol = $('#symbol')?.value, result = $('[data-order-result]');
    if (!account || !symbol) { if (result) { result.hidden = false; result.textContent = 'Select a connected broker account and instrument first.'; } return; }
    const form = new FormData(event.currentTarget), button = $('.execute-btn');
    if (button) { button.disabled = true; button.textContent = 'Submitting…'; }
    try {
      const payload = {account: account.id, symbol, direction, order_type: form.get('order_type'), stake: form.get('stake'), strategy: form.get('strategy') || '', client_order_id: `ui-${crypto.randomUUID?.() || Date.now()}`, routing_context: window.__algobotAiOrderContext || {}};
      const order = await api('/api/orders/', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}, 25000);
      if (result) { result.hidden = false; result.textContent = `Order ${order.broker_order_id || order.id || ''} ${order.status || 'submitted'}.`; }
      window.__algobotAiOrderContext = null; await loadRecords();
    } catch (e) { if (result) { result.hidden = false; result.textContent = `Order rejected: ${e.message || 'request failed'}`; } }
    finally { if (button) { button.disabled = false; button.textContent = 'Place order'; } }
  }

  function boot() {
    if (!$('.terminal-page')) return;
    $('[data-order-form]')?.addEventListener('submit', submitOrder);
    $('[data-action="terminal-refresh"]')?.addEventListener('click', refresh);
    $('#symbol')?.addEventListener('change', () => { loadQuote(); loadRecords(); });
    $('#account')?.addEventListener('change', () => { renderAccount(selectedAccount()); loadQuote(); loadRecords(); });
    document.querySelectorAll('[data-direction]').forEach(b => b.addEventListener('click', () => { direction = b.dataset.direction; document.querySelectorAll('[data-direction]').forEach(x => x.classList.toggle('active', x === b)); }));
    window.addEventListener('algobot:backend-accounts-loaded', e => { renderAccounts(e.detail); loadQuote(); loadRecords(); });
    window.addEventListener('algobot:account-synced', e => { renderAccounts((window.AlgoBotBrokerAccounts || accounts).map(a => String(a.id) === String(e.detail?.id) ? e.detail : a)); loadQuote(); loadRecords(); });
    window.AlgoBotBrokerState?.subscribe(() => { loadQuote(); loadRecords(); });
    refresh();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true}); else boot();
})();
