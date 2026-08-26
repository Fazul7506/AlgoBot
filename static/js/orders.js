(() => {
  'use strict';
  if (window.__algoBotOrdersPage) return;
  window.__algoBotOrdersPage = true;

  const $ = selector => document.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' })[c]);
  let rows = [];

  function render(message = null, state = 'Ready') {
    const table = $('[data-page-table]');
    if (!table) return;
    const status = $('[data-page-status]');
    const count = $('[data-record-count]');
    const updated = $('[data-page-updated]');
    const risk = $('[data-page-risk]');
    if (message) {
      if (status) status.textContent = state;
      if (count) count.textContent = '—';
      if (updated) updated.textContent = '—';
      if (risk) risk.textContent = '—';
      table.querySelector('thead').innerHTML = '';
      table.querySelector('tbody').innerHTML = `<tr class="empty-row"><td>${esc(message)}</td></tr>`;
      return;
    }
    if (status) status.textContent = 'Ready';
    if (count) count.textContent = String(rows.length);
    if (updated) updated.textContent = new Date().toLocaleTimeString();
    if (risk) risk.textContent = String(rows.filter(row => ['rejected', 'failed', 'cancelled'].includes(String(row.status || '').toLowerCase())).length);
    if (!rows.length) {
      table.querySelector('thead').innerHTML = '';
      table.querySelector('tbody').innerHTML = '<tr class="empty-row"><td>No orders have been returned by the authenticated execution API yet.</td></tr>';
      return;
    }
    table.querySelector('thead').innerHTML = '<tr><th>Symbol</th><th>Side</th><th>Type</th><th>Quantity</th><th>Requested</th><th>Status</th><th>Broker order</th><th>Created</th></tr>';
    table.querySelector('tbody').innerHTML = rows.map(row => `<tr><td><strong>${esc(row.symbol || '—')}</strong></td><td>${esc(row.direction || '—')}</td><td>${esc(row.order_type || '—')}</td><td>${esc(row.quantity ?? row.stake ?? '—')}</td><td>${esc(row.price ?? 'Market')}</td><td><span class="badge">${esc(row.status || 'unknown')}</span></td><td>${esc(row.broker_order_id || 'Pending/unknown')}</td><td>${esc(row.created_at ? new Date(row.created_at).toLocaleString() : '—')}</td></tr>`).join('');
  }

  async function load() {
    render('Loading authenticated broker orders…', 'Loading');
    try {
      const payload = await window.AlgoBotFrontendData.request('/api/orders/');
      rows = list(payload);
      render();
    } catch (error) {
      rows = [];
      render(`Orders unavailable: ${error?.message || 'The backend did not return an order response.'}`, 'Error');
    }
  }

  function filter() {
    const query = String($('[data-page-search]')?.value || '').trim().toLowerCase();
    document.querySelectorAll('[data-page-table] tbody tr').forEach(row => {
      row.hidden = !!query && !row.textContent.toLowerCase().includes(query);
    });
  }

  function boot() {
    // The authenticated API is the source of truth. Do not block orders behind
    // a separate client-side broker-state cache; that cache can be stale while
    // the broker-backed API is already available.
    window.AlgoBotBrokerState?.subscribe(() => load());
    $('[data-page-search]')?.addEventListener('input', filter);
    load();
    window.setInterval(load, 30000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
