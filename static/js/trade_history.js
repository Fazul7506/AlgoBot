(() => {
  'use strict';
  if (window.__algoBotTradeHistory) return;
  window.__algoBotTradeHistory = true;

  const $ = selector => document.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' })[c]);
  let rows = [];

  function render(message = null) {
    const table = $('[data-history-table]');
    if (!table) return;
    const status = $('[data-history-status]');
    const count = $('[data-history-count]');
    const updated = $('[data-history-updated]');
    if (message) {
      if (status) status.textContent = message;
      if (count) count.textContent = '—';
      if (updated) updated.textContent = '—';
      table.querySelector('thead').innerHTML = '';
      table.querySelector('tbody').innerHTML = `<tr class="empty-row"><td>${esc(message)}</td></tr>`;
      return;
    }
    if (status) status.textContent = 'Ready';
    if (count) count.textContent = String(rows.length);
    if (updated) updated.textContent = new Date().toLocaleTimeString();
    if (!rows.length) {
      table.querySelector('thead').innerHTML = '';
      table.querySelector('tbody').innerHTML = '<tr class="empty-row"><td>No confirmed execution records are available yet.</td></tr>';
      return;
    }
    table.querySelector('thead').innerHTML = '<tr><th>Order</th><th>Event</th><th>Status</th><th>Latency</th><th>Message</th><th>Created</th></tr>';
    table.querySelector('tbody').innerHTML = rows.map(row => `<tr><td>${esc(row.order ?? '—')}</td><td>${esc(row.event || '—')}</td><td><span class="badge">${esc(row.status || 'unknown')}</span></td><td>${esc(row.latency ?? '—')}</td><td>${esc(row.message || '—')}</td><td>${esc(row.created_at ? new Date(row.created_at).toLocaleString() : '—')}</td></tr>`).join('');
  }

  async function load() {
    render('Loading execution history…');
    try {
      const payload = await window.AlgoBotFrontendData.request('/api/execution/logs/');
      rows = list(payload);
      render();
    } catch (error) {
      rows = [];
      render(`Execution history unavailable: ${error.message}`);
    }
  }

  function filter() {
    const query = String($('[data-history-search]')?.value || '').trim().toLowerCase();
    document.querySelectorAll('[data-history-table] tbody tr').forEach(row => {
      row.hidden = !!query && !row.textContent.toLowerCase().includes(query);
    });
  }

  function boot() {
    $('[data-history-search]')?.addEventListener('input', filter);
    load();
    window.setInterval(load, 30000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
