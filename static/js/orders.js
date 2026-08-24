(() => {
  'use strict';
  if (window.__algoBotOrdersPage) return;
  window.__algoBotOrdersPage = true;

  const $ = selector => document.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' })[c]);
  let rows = [];

  function connected() {
    const state = window.AlgoBotBrokerState?.get();
    return !!state?.account && ['CONNECTED', 'SYNCING', 'READY', 'DEGRADED'].includes(state.status);
  }

  function render(message = null) {
    const table = $('[data-page-table]');
    if (!table) return;
    const status = $('[data-page-status]');
    const count = $('[data-record-count]');
    const updated = $('[data-page-updated]');
    const risk = $('[data-page-risk]');
    if (message) {
      if (status) status.textContent = message;
      if (count) count.textContent = '—';
      table.querySelector('thead').innerHTML = '';
      table.querySelector('tbody').innerHTML = `<tr class="empty-row"><td>${esc(message)}</td></tr>`;
      return;
    }
    if (status) status.textContent = 'Ready';
    if (count) count.textContent = String(rows.length);
    if (updated) updated.textContent = new Date().toLocaleTimeString();
    if (risk) risk.textContent = String(rows.filter(row => ['rejected', 'failed'].includes(String(row.status || '').toLowerCase())).length);
    if (!rows.length) {
      table.querySelector('thead').innerHTML = '';
      table.querySelector('tbody').innerHTML = '<tr class="empty-row"><td>No orders reported by the broker-backed execution API.</td></tr>';
      return;
    }
    table.querySelector('thead').innerHTML = '<tr><th>Symbol</th><th>Side</th><th>Type</th><th>Quantity</th><th>Requested</th><th>Status</th><th>Broker order</th><th>Created</th></tr>';
    table.querySelector('tbody').innerHTML = rows.map(row => `<tr><td><strong>${esc(row.symbol)}</strong></td><td>${esc(row.direction || '—')}</td><td>${esc(row.order_type || '—')}</td><td>${esc(row.quantity ?? row.stake ?? '—')}</td><td>${esc(row.price ?? 'Market')}</td><td><span class="badge">${esc(row.status || 'unknown')}</span></td><td>${esc(row.broker_order_id || 'Pending/unknown')}</td><td>${esc(row.created_at ? new Date(row.created_at).toLocaleString() : '—')}</td></tr>`).join('');
  }

  async function load() {
    if (!connected()) { rows = []; render('Connect a broker to view execution orders.'); return; }
    render('Synchronizing broker-backed orders…');
    try { rows = list(await window.AlgoBotFrontendData.request('/api/orders/')); render(); }
    catch (error) { rows = []; render(`Orders unavailable: ${error.message}`); }
  }

  function filter() {
    const query = String($('[data-page-search]')?.value || '').trim().toLowerCase();
    document.querySelectorAll('[data-page-table] tbody tr').forEach(row => { row.hidden = !!query && !row.textContent.toLowerCase().includes(query); });
  }

  function boot() {
    window.AlgoBotBrokerState?.subscribe(event => {
      if (['NO_BROKER', 'DISCONNECTED'].includes(event.detail.state.status)) render('Connect a broker to view execution orders.');
      else if (['READY', 'CONNECTED'].includes(event.detail.state.status)) load();
    });
    $('[data-page-search]')?.addEventListener('input', filter);
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
