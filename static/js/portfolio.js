(() => {
  'use strict';
  if (window.__algoBotPortfolioPage) return;
  window.__algoBotPortfolioPage = true;

  const $ = selector => document.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' })[c]);

  async function load() {
    const table = $('[data-page-table]');
    if (!table) return;
    const status = $('[data-page-status]');
    const count = $('[data-record-count]');
    const updated = $('[data-page-updated]');
    const risk = $('[data-page-risk]');
    try {
      if (status) status.textContent = 'Synchronizing';
      const [portfolio, performance, exposure] = await Promise.all([
        window.AlgoBotFrontendData.request('/api/portfolio/'),
        window.AlgoBotFrontendData.request('/api/portfolio/performance/'),
        window.AlgoBotFrontendData.request('/api/portfolio/exposure/')
      ]);
      const rows = list(portfolio);
      const performanceRows = list(performance);
      const exposureRows = list(exposure);
      const combined = rows.length ? rows : (performanceRows.length ? performanceRows : exposureRows);
      if (count) count.textContent = String(combined.length);
      if (updated) updated.textContent = new Date().toLocaleTimeString();
      if (risk) {
        const exposureValue = exposureRows.reduce((sum, row) => sum + Number(row.exposure_value || row.value || 0), 0);
        risk.textContent = exposureRows.length ? exposureValue.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—';
      }
      if (status) status.textContent = 'Ready';
      if (!combined.length) {
        table.querySelector('thead').innerHTML = '';
        table.querySelector('tbody').innerHTML = '<tr class="empty-row"><td>No portfolio records returned by the backend.</td></tr>';
        return;
      }
      const keys = [...new Set(combined.flatMap(row => Object.keys(row || {})))].slice(0, 10);
      table.querySelector('thead').innerHTML = `<tr>${keys.map(key => `<th>${esc(key.replaceAll('_', ' '))}</th>`).join('')}</tr>`;
      table.querySelector('tbody').innerHTML = combined.slice(0, 100).map(row => `<tr>${keys.map(key => `<td>${esc(typeof row[key] === 'object' ? JSON.stringify(row[key]) : row[key])}</td>`).join('')}</tr>`).join('');
    } catch (error) {
      if (status) status.textContent = 'Backend unavailable';
      if (count) count.textContent = '—';
      table.querySelector('thead').innerHTML = '';
      table.querySelector('tbody').innerHTML = `<tr class="empty-row"><td>${esc(`Portfolio unavailable: ${error.message}`)}</td></tr>`;
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
