(() => {
  'use strict';

  const page = document.querySelector('[data-page="core-performance"]');
  if (!page) return;

  const $ = (selector, root = document) => root.querySelector(selector);

  const request = async (url) => {
    const response = await fetch(url, {
      credentials: 'same-origin',
      headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      cache: 'no-store'
    });
    const text = await response.text();
    let payload = {};
    try { payload = text ? JSON.parse(text) : {}; } catch { payload = { detail: text }; }
    if (response.status === 401 || response.status === 403) {
      window.location.assign('/login/?next=' + encodeURIComponent(window.location.pathname));
      throw new Error('Authentication required');
    }
    if (!response.ok) throw new Error(payload.detail || payload.message || `Request failed (${response.status})`);
    return payload;
  };

  const normalise = (value) => {
    if (Array.isArray(value)) return value;
    if (Array.isArray(value?.results)) return value.results;
    if (Array.isArray(value?.data)) return value.data;
    if (value?.data && typeof value.data === 'object') return [value.data];
    if (value && typeof value === 'object') return [value];
    return [];
  };

  const money = (value) => {
    if (value === null || value === undefined || value === '') return '—';
    const number = Number(value);
    return Number.isFinite(number) ? number.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—';
  };

  const pct = (value) => {
    if (value === null || value === undefined || value === '') return '—';
    const number = Number(value);
    return Number.isFinite(number) ? `${number.toFixed(1)}%` : '—';
  };

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  })[c]);

  function setStatus(text, detail) {
    const status = $('[data-workspace-status]', page);
    const message = $('[data-workspace-message]', page);
    if (status) status.textContent = text;
    if (message) message.textContent = detail;
  }

  function renderMetrics(data) {
    const metrics = data?.data?.metrics || data?.data || data?.metrics || {};
    const workspace = $('[data-module-workspace]', page);
    if (!workspace) return;

    const hasMetrics = Object.keys(metrics).length > 0;
    const rows = [
      ['Total trades', metrics.total_trades ?? 0],
      ['Winning trades', metrics.winning_trades ?? 0],
      ['Losing trades', metrics.losing_trades ?? 0],
      ['Win rate', pct(metrics.win_rate)],
      ['Total profit', money(metrics.total_profit)],
      ['Average profit', money(metrics.average_profit)],
      ['Sharpe ratio', metrics.sharpe_ratio ?? '—'],
      ['Best trade', money(metrics.best_trade)],
      ['Worst trade', money(metrics.worst_trade)]
    ];

    workspace.innerHTML = `
      <div class="module-card-grid">
        <article class="panel module-focus">
          <p class="eyebrow">Live performance</p>
          <h2>${hasMetrics ? 'Trading performance summary' : 'Performance workspace ready'}</h2>
          <p>${hasMetrics ? 'Metrics below are calculated from your authenticated closed-trade records.' : 'No closed trades have been returned yet. Once trades close, performance metrics will appear here automatically.'}</p>
          <div class="metric-grid">
            ${rows.map(([label, value]) => `<div class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join('')}
          </div>
        </article>
        <article class="panel">
          <p class="eyebrow">Analytics</p>
          <h2>Advanced analysis</h2>
          <p>Use the authenticated performance API for deeper metrics, strategy comparison and export without inventing values when the account has no history.</p>
          <div class="action-list">
            <a class="action-link" href="/analytics/">Open analytics <span>→</span></a>
            <a class="action-link" href="/api/dashboard/performance_metrics/" target="_blank" rel="noreferrer">Performance metrics API <span>→</span></a>
          </div>
        </article>
        <article class="panel">
          <p class="eyebrow">Execution path</p>
          <h2>Trade safely</h2>
          <p>Performance is read-only analytics. Execution remains subject to broker connection and risk controls.</p>
          <div class="control-stack">
            <a class="btn primary" href="/trading/">Open trading terminal</a>
            <a class="btn ghost" href="/risk/">Open risk center</a>
          </div>
        </article>
      </div>`;
  }

  async function loadPerformance() {
    setStatus('Synchronising performance', 'Reading authenticated trading history and account data.');
    try {
      const [summary, overview] = await Promise.all([
        request('/api/dashboard/performance_summary/'),
        request('/api/dashboard/account_overview/')
      ]);

      renderMetrics(summary);

      const overviewData = overview?.data || {};
      const stats = overviewData.trading_stats || {};
      const account = overviewData.account || {};
      const balance = $('[data-kpi="balance"]', page);
      const positions = $('[data-kpi="positions"]', page);
      const winrate = $('[data-kpi="winrate"]', page);
      const pnl = $('[data-kpi="pnl"]', page);
      if (balance) balance.textContent = account.balance != null ? `${account.currency || ''} ${money(account.balance)}`.trim() : '—';
      if (positions) positions.textContent = stats.open_trades ?? 0;
      if (winrate) winrate.textContent = pct(stats.win_rate);
      if (pnl) pnl.textContent = money(stats.total_pnl);

      const metrics = summary?.data?.metrics || summary?.data || {};
      const hasRecords = Object.keys(metrics).length > 0 && !summary?.data?.message;
      setStatus('Backend connected', hasRecords ? 'Live performance metrics loaded successfully.' : 'Backend connected. No closed trades have been recorded yet.');
    } catch (error) {
      setStatus('Backend partially unavailable', error.message || 'Unable to load performance data.');
      const workspace = $('[data-module-workspace]', page);
      if (workspace) {
        workspace.innerHTML = `<div class="panel"><p class="eyebrow">Performance service</p><h2>Unable to load live metrics</h2><p>${escapeHtml(error.message || 'The performance API did not respond successfully.')}</p><div class="control-stack"><button class="btn primary" type="button" data-performance-retry>Retry</button><a class="btn ghost" href="/monitoring/">Open monitoring</a></div></div>`;
        $('[data-performance-retry]', workspace)?.addEventListener('click', loadPerformance);
      }
    }
  }

  const refresh = $('[data-action="refresh"]', page);
  refresh?.addEventListener('click', (event) => { event.preventDefault(); loadPerformance(); });

  const reload = $('[data-action="reload-records"]', page);
  reload?.addEventListener('click', (event) => { event.preventDefault(); loadPerformance(); });

  loadPerformance();
})();
