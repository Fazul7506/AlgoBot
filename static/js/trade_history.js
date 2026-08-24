(() => {
  'use strict';
  if (window.__algoBotTradeHistory) return;
  window.__algoBotTradeHistory = true;

  const $ = selector => document.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' })[c]);
  let rows = [];

  function connected() {
    const state = window.AlgoBotBrokerState?.get();
    return !!state?.account && ['CONNECTED', 'SYNCING', 'READY', 'DEGRADED'].includes(state.status);
  }

  function render(message = null) {
    const table = $('[data-history-table]');
    if (!table) return;
    if (message) {
      $('[data-history-status]').textContent = message;
      $('[data-history-count]').textContent = '—';
      table.querySelector('thead').innerHTML = '';
      table.querySelector('tbody').innerHTML = `<tr class="empty-row"><td>${esc(message)}</td></tr>`;
      return;
    }
    $('[data-history-status]').textContent = 'Ready';
    $('[data-history-count]').textContent = String(rows.length);
    $('[data-history-updated]').textContent = new Date().toLocaleTimeString();
    if (!rows.length) {
      table.querySelector('thead').innerHTML = '';
      table.querySelector('tbody').innerHTML = '<tr class="empty-row"><td>No confirmed execution reports are available.</td></tr>';
      return;
    }
    table.querySelector('thead').innerHTML = '<tr><th>Order</th><th>Symbol</th><th>Requested</th><th>Execution</th><th>Slippage</th><th>Fees</th><th>Status</th><th>Created</th></tr>';
    table.querySelector('tbody').innerHTML = rows.map(row => `<tr><td>${esc(row.order)}</td><td>${esc(row.symbol || row.order_symbol || '—')}</td><td>${esc(row.requested_price ?? '—')}</td><td>${esc(row.execution_price ?? '—')}</td><td>${esc(row.slippage ?? '—')}</td><td>${esc(row.fees ?? '—')}</td><td><span class="badge">${esc(row.status || 'unknown')}</span></td><td>${esc(row.created_at ? new Date(row.created_at).toLocaleString() : '—')}</td></tr>`).join('');
  }

  async function load() {
    if (!connected()) { rows = []; render('Connect a broker to view confirmed execution history.'); return; }
    render('Synchronizing execution reports…');
    try { rows = list(await window.AlgoBotFrontendData.request('/api/executions/')); render(); }
    catch (error) { rows = []; render(`Execution history unavailable: ${error.message}`); }
  }

  function filter() {
    const query = String($('[data-history-search]')?.value || '').trim().toLowerCase();
    document.querySelectorAll('[data-history-table] tbody tr').forEach(row => { row.hidden = !!query && !row.textContent.toLowerCase().includes(query); });
  }

  function boot() {
    window.AlgoBotBrokerState?.subscribe(event => {
      if (['NO_BROKER', 'DISCONNECTED'].includes(event.detail.state.status)) render('Connect a broker to view confirmed execution history.');
      else if (['READY', 'CONNECTED'].includes(event.detail.state.status)) load();
    });
    $('[data-history-search]')?.addEventListener('input', filter);
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
