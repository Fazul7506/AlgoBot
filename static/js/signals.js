(() => {
  'use strict';
  if (window.__algoBotSignalsPage) return;
  window.__algoBotSignalsPage = true;

  const $ = selector => document.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' })[c]);
  let rows = [];

  async function load() {
    const table = $('[data-page-table]');
    if (!table) return;
    const status = $('[data-page-status]');
    const count = $('[data-record-count]');
    const updated = $('[data-page-updated]');
    const risk = $('[data-page-risk]');
    try {
      if (status) status.textContent = 'Loading backend signals';
      rows = list(await window.AlgoBotFrontendData.request('/api/strategy-signals/?limit=100', {}, 8000));
      if (count) count.textContent = String(rows.length);
      if (updated) updated.textContent = new Date().toLocaleTimeString();
      if (risk) {
        const avg = rows.length ? rows.reduce((sum, row) => sum + Number(row.confidence || 0), 0) / rows.length : null;
        risk.textContent = avg == null ? '—' : `${avg.toFixed(1)}% confidence`;
      }
      if (status) status.textContent = 'Ready';
      if (!rows.length) {
        table.querySelector('thead').innerHTML = '';
        table.querySelector('tbody').innerHTML = '<tr class="empty-row"><td>No strategy signals returned.</td></tr>';
        return;
      }
      table.querySelector('thead').innerHTML = '<tr><th>Symbol</th><th>Direction</th><th>Confidence</th><th>Regime</th><th>Strategy</th><th>Executed</th><th>Created</th></tr>';
      table.querySelector('tbody').innerHTML = rows.map(row => `<tr><td><strong>${esc(row.symbol)}</strong></td><td>${esc(row.direction || '—')}</td><td>${row.confidence == null ? '—' : `${Number(row.confidence).toFixed(1)}%`}</td><td>${esc(row.market_regime || '—')}</td><td>${esc(row.strategy || '—')}</td><td>${row.was_executed ? 'Yes' : 'No'}</td><td>${esc(row.created_at ? new Date(row.created_at).toLocaleString() : '—')}</td></tr>`).join('');
    } catch (error) {
      rows = [];
      if (status) status.textContent = 'Backend unavailable';
      if (count) count.textContent = '—';
      table.querySelector('thead').innerHTML = '';
      table.querySelector('tbody').innerHTML = `<tr class="empty-row"><td>${esc(`Signals unavailable: ${error.message}`)}</td></tr>`;
    }
  }

  function filter() {
    const query = String($('[data-page-search]')?.value || '').trim().toLowerCase();
    document.querySelectorAll('[data-page-table] tbody tr').forEach(row => { row.hidden = !!query && !row.textContent.toLowerCase().includes(query); });
  }

  function boot() {
    $('[data-page-search]')?.addEventListener('input', filter);
    window.addEventListener('algobot:account-synced', load);
    window.AlgoBotBrokerState?.subscribe(event => {
      if (['READY', 'CONNECTED', 'DEGRADED'].includes(event.detail.state.status)) load();
    });
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
