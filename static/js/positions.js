(() => {
  'use strict';
  if (window.__algoBotPositionsPage) return;
  window.__algoBotPositionsPage = true;

  const $ = selector => document.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' })[c]);
  let rows = [];

  function isConnected() {
    const state = window.AlgoBotBrokerState?.get();
    return !!state?.account && ['CONNECTED', 'SYNCING', 'READY', 'DEGRADED'].includes(state.status);
  }

  function render(message = null) {
    const table = $('[data-page-table]');
    const status = $('[data-page-status]');
    const count = $('[data-record-count]');
    const updated = $('[data-page-updated]');
    if (!table) return;
    if (message) {
      if (status) status.textContent = message;
      table.querySelector('thead').innerHTML = '';
      table.querySelector('tbody').innerHTML = `<tr class="empty-row"><td>${esc(message)}</td></tr>`;
      if (count) count.textContent = '—';
      return;
    }
    if (status) status.textContent = 'Ready';
    if (count) count.textContent = String(rows.length);
    if (updated) updated.textContent = new Date().toLocaleTimeString();
    const risk = rows.reduce((sum, row) => sum + Math.abs(Number(row.profit ?? 0)), 0);
    const riskNode = $('[data-page-risk]');
    if (riskNode) riskNode.textContent = risk ? risk.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '0';
    if (!rows.length) {
      table.querySelector('thead').innerHTML = '';
      table.querySelector('tbody').innerHTML = '<tr class="empty-row"><td>No open positions reported by the broker-backed API.</td></tr>';
      return;
    }
    table.querySelector('thead').innerHTML = '<tr><th>Symbol</th><th>Side</th><th>Size</th><th>Entry</th><th>Current</th><th>P/L</th><th>Status</th></tr>';
    table.querySelector('tbody').innerHTML = rows.map(row => `<tr><td><strong>${esc(row.symbol)}</strong></td><td>${esc(row.direction || row.side || '—')}</td><td>${esc(row.size ?? '—')}</td><td>${esc(row.entry_price ?? '—')}</td><td>${esc(row.current_price ?? '—')}</td><td>${esc(row.profit ?? '—')}</td><td><span class="badge">${esc(row.status || 'open')}</span></td></tr>`).join('');
  }

  async function load() {
    if (!isConnected()) {
      rows = [];
      render('Connect a broker to view live positions.');
      return;
    }
    render('Synchronizing broker positions…');
    try {
      rows = list(await window.AlgoBotFrontendData.request('/api/positions/open/'));
      render();
    } catch (error) {
      rows = [];
      render(`Positions unavailable: ${error.message}`);
    }
  }

  function filter() {
    const query = String($('[data-page-search]')?.value || '').trim().toLowerCase();
    document.querySelectorAll('[data-page-table] tbody tr').forEach(row => { row.hidden = !!query && !row.textContent.toLowerCase().includes(query); });
  }

  function boot() {
    window.AlgoBotBrokerState?.subscribe(event => {
      if (event.detail.state.status === 'DISCONNECTED' || event.detail.state.status === 'NO_BROKER') render('Connect a broker to view live positions.');
      else if (['READY', 'CONNECTED'].includes(event.detail.state.status)) load();
    });
    $('[data-page-search]')?.addEventListener('input', filter);
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
