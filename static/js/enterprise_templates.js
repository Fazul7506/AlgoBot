(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  const json = async (url, opts = {}) => {
    const shared = window.AlgoBotFrontendData?.request;
    if (typeof shared === 'function') {
      try { return await shared(url, { ...opts, notifyOnError: false }, opts.__timeoutMs || 25000); }
      catch (error) {
        if (error?.status === 401 || error?.status === 403) {
          document.body.classList.add('auth-expired');
          window.location.assign('/login/?next=' + encodeURIComponent(window.location.pathname));
        }
        throw error;
      }
    }
    const headers = { Accept: 'application/json', ...(opts.headers || {}) };
    const res = await fetch(url, { credentials: 'same-origin', ...opts, headers });
    const text = await res.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }
    if (res.status === 401 || res.status === 403) { document.body.classList.add('auth-expired'); window.location.assign('/login/?next=' + encodeURIComponent(window.location.pathname)); throw new Error('Authentication required'); }
    if (!res.ok) throw new Error(data.detail || data.message || `Request failed (${res.status})`);
    return data;
  };

  const csrf = () => {
    const cookie = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return cookie ? decodeURIComponent(cookie[1]) : '';
  };

  const toast = (message, type = 'info') => {
    let stack = $('.toast-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'toast-stack';
      document.body.appendChild(stack);
    }
    const node = document.createElement('div');
    node.className = `toast ${type}`;
    node.textContent = message;
    stack.appendChild(node);
    setTimeout(() => node.remove(), 3500);
  };

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  })[c]);
  const money = value => value === null || value === undefined || value === '' ? '—' : Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const pct = value => value === null || value === undefined || value === '' ? '—' : `${Number(value).toFixed(1)}%`;
  const normalise = value => Array.isArray(value) ? value : (
    Array.isArray(value?.results) ? value.results : (
      Array.isArray(value?.data) ? value.data : (
        value?.data && typeof value.data === 'object' ? [value.data] : []
      )
    )
  );

  const endpointMap = {
    trading: ['/api/orders/', '/api/positions/open/', '/api/dashboard/signals/'],
    markets: ['/api/market/symbols/', '/api/market/snapshots/all_snapshots/', '/api/market/stats/'],
    strategies: ['/api/strategies/', '/api/strategies/signals/', '/api/strategies/performance/'],
    backtesting: ['/api/backtests/', '/api/statistics/', '/api/paper/account/', '/api/optimization/results/'],
    ai: ['/api/ai/models/', '/api/ai/predictions/', '/api/ai/recommendations/', '/api/ai/training-jobs/'],
    risk: ['/api/risk/profile/', '/api/risk/assessment/', '/api/risk/exposure/', '/api/risk/drawdown/', '/api/risk/kill-switch/'],
    portfolio: ['/api/portfolio/', '/api/portfolio/performance/', '/api/portfolio/exposure/', '/api/portfolio/allocation/'],
    automation: ['/api/automation/workflows/', '/api/automation/events/', '/api/automation/rules/', '/api/automation/history/'],
    monitoring: ['/api/monitoring/dashboard/', '/api/monitoring/health/', '/api/monitoring/trading/', '/api/metrics/'],
    brokers: ['/api/brokers/', '/api/brokers/accounts/', '/api/broker-health/'],
    notifications: ['/api/notifications/'],
    developer: ['/api/developer/keys/', '/api/developer/docs/', '/api/developer/plugins/', '/api/developer/webhooks/'],
    deployment: ['/api/system/health/', '/api/system/status/', '/api/system/version/', '/api/system/backups/'],
    smart_money: ['/api/smc/'],
    indicators: ['/api/market/indicators/', '/api/market/signals/', '/api/market/profiles/'],
    copy_trading: ['/api/copy-trading/leaderboard/', '/api/copy-trading/my_following/', '/api/copy-trading/copied_trades/'],
    enterprise: ['/api/enterprise/'],
    analytics: ['/api/dashboard/performance_summary/', '/api/dashboard/performance_metrics/']
  };

  const moduleKey = page => {
    const raw = (page.dataset.module || '').toLowerCase().replace(/\s+/g, '_');
    if (raw.includes('market')) return 'markets';
    if (raw.includes('strategy')) return 'strategies';
    if (raw.includes('backtest')) return 'backtesting';
    if (raw.includes('risk')) return 'risk';
    if (raw.includes('portfolio')) return 'portfolio';
    if (raw.includes('automation')) return 'automation';
    if (raw.includes('monitor')) return 'monitoring';
    if (raw.includes('broker')) return 'brokers';
    if (raw.includes('notification')) return 'notifications';
    if (raw.includes('developer')) return 'developer';
    if (raw.includes('deploy')) return 'deployment';
    if (raw.includes('smart')) return 'smart_money';
    if (raw.includes('indicator')) return 'indicators';
    if (raw.includes('copy')) return 'copy_trading';
    if (raw.includes('enterprise')) return 'enterprise';
    if (raw === 'ai' || raw.includes('intelligence')) return 'ai';
    if (raw.includes('analytic')) return 'analytics';
    return raw.includes('trading') || page.dataset.page?.includes('trading') ? 'trading' : 'general';
  };

  async function accountKPIs() {
    if (document.querySelector('[data-dashboard-command]')) return null;
    try {
      const [overview, accounts] = await Promise.all([
        json('/api/dashboard/account_overview/'),
        json('/api/brokers/accounts/')
      ]);
      const data = overview.data || {};
      const stats = data.trading_stats || {};
      const accountsList = normalise(accounts);
      const selected = window.AlgoBotAccountContext?.getSelected?.();
      const account = selected || accountsList.find(x => x.is_active === true) || (accountsList.length === 1 ? accountsList[0] : null) || data.account || null;
      const balance = $('[data-kpi="balance"]');
      const positions = $('[data-kpi="positions"]');
      const winrate = $('[data-kpi="winrate"]');
      const pnl = $('[data-kpi="pnl"]');
      if (balance) balance.textContent = account ? `${account.currency || ''} ${money(account.balance)}`.trim() : '—';
      if (positions) positions.textContent = stats.open_trades ?? '0';
      if (winrate) winrate.textContent = pct(stats.win_rate);
      if (pnl) pnl.textContent = money(stats.total_pnl);
      const terminalAccount = $('[data-terminal-account]');
      if (terminalAccount) terminalAccount.textContent = `Account: ${account?.broker_account_id || account?.account_id || data.account?.account_id || 'Not connected'}`;
      return { ...data, selectedAccount: account };
    } catch (error) {
      toast(`Account data unavailable: ${error.message}`, 'error');
      return null;
    }
  }

  function renderTable(rows, tableElement, maxRows = 50) {
    if (!tableElement) return;
    const list = normalise(rows);
    const thead = tableElement.querySelector('thead');
    const tbody = tableElement.querySelector('tbody');
    if (!list.length) {
      if (thead) thead.innerHTML = '';
      if (tbody) tbody.innerHTML = '<tr class="empty-row"><td>No records returned by the backend.</td></tr>';
      return;
    }
    const keys = [...new Set(list.flatMap(row => Object.keys(row || {})))].slice(0, 10);
    if (thead) thead.innerHTML = `<tr>${keys.map(k => `<th>${escapeHtml(k.replaceAll('_', ' '))}</th>`).join('')}</tr>`;
    if (tbody) tbody.innerHTML = list.slice(0, maxRows).map(row => `<tr>${keys.map(k => {
      const value = typeof row[k] === 'object' ? JSON.stringify(row[k]) : row[k];
      return `<td>${escapeHtml(value)}</td>`;
    }).join('')}</tr>`).join('');
  }

  const moduleLinks = {
    markets: [['/markets/', 'Market workspace'], ['/api/market/symbols/', 'Symbol universe']],
    strategies: [['/strategies/', 'Strategy manager'], ['/api/strategies/', 'Strategy API']],
    backtesting: [['/backtesting/', 'Backtest lab'], ['/api/backtests/', 'Backtest records']],
    ai: [['/predictions/', 'Prediction center'], ['/api/ai/models/', 'Model registry']],
    risk: [['/risk/', 'Risk center'], ['/api/risk/profile/', 'Risk profiles']],
    portfolio: [['/portfolio/', 'Portfolio workspace'], ['/api/portfolio/', 'Portfolios']],
    analytics: [['/performance/', 'Performance'], ['/analytics/', 'Analytics']],
    brokers: [['/brokers/', 'Broker marketplace'], ['/brokers/connect/', 'Connect broker']],
    automation: [['/api/automation/workflows/', 'Workflows'], ['/api/automation/rules/', 'Rules']],
    monitoring: [['/monitoring/', 'Monitoring'], ['/api/monitoring/health/', 'Health API']],
    notifications: [['/api/notifications/', 'Notification center']],
    indicators: [['/api/market/indicators/', 'Indicator values'], ['/api/market/signals/', 'Technical signals']],
    smart_money: [['/api/smc/', 'Smart Money API']],
    copy_trading: [['/api/copy-trading/leaderboard/', 'Leader board'], ['/api/copy-trading/my_following/', 'My following']],
    developer: [['/api/developer/docs/', 'API docs'], ['/api/developer/plugins/', 'Plugins']],
    deployment: [['/api/system/status/', 'System status'], ['/api/system/health/', 'System health']],
    enterprise: [['/api/enterprise/', 'Enterprise API']]
  };

  async function genericWorkspace(page) {
    const key = moduleKey(page);
    const urls = endpointMap[key] || [];
    const workspace = $('[data-module-workspace]', page);
    const resourceList = $('[data-resource-list]', page);
    const status = $('[data-workspace-status]', page);
    const message = $('[data-workspace-message]', page);
    const links = moduleLinks[key] || [['/trading/', 'Trading terminal'], ['/orders/', 'Orders'], ['/positions/', 'Positions']];

    if (resourceList) resourceList.innerHTML = urls.map(url => `<a href="${url}" target="_blank" rel="noreferrer">${escapeHtml(url.replace('/api/', ''))}</a>`).join('');
    if (status) status.textContent = 'Synchronising backend';
    if (message) message.textContent = `${key.replaceAll('_', ' ')} controls are live and permission-scoped.`;

    if (workspace) {
      workspace.innerHTML = `<div class="module-card-grid">
        <article class="panel module-focus">
          <p class="eyebrow">Live module</p>
          <h2>${escapeHtml(page.dataset.module || 'Workspace')}</h2>
          <p>This workspace is driven by the existing Django/DRF backend. Use the controls below to move from analysis to execution.</p>
          <div class="action-list">${links.map(([href, label]) => `<a class="action-link" href="${href}">${escapeHtml(label)} <span>→</span></a>`).join('')}</div>
        </article>
        <article class="panel">
          <p class="eyebrow">Execution path</p>
          <h2>Trade from here</h2>
          <p>Market data → signal → risk assessment → order → broker execution → position → analytics.</p>
          <div class="control-stack"><a class="btn primary" href="/trading/">Open trading terminal</a><button class="btn ghost" data-action="module-refresh">Sync backend</button></div>
        </article>
        <article class="panel">
          <p class="eyebrow">Controls</p>
          <h2>Operational state</h2>
          <div class="health-stack"><span><b></b> Authentication active</span><span><b></b> User-scoped data</span><span><b></b> API routing available</span><span><b></b> Risk controls retained</span></div>
        </article>
      </div>`;
      $('[data-action="module-refresh"]', page)?.addEventListener('click', () => genericWorkspace(page));
    }

    try {
      if (urls[0]) {
        const data = await json(urls[0]);
        renderTable(data, $('[data-enterprise-table]', page));
        const activity = $('[data-activity-list]', page);
        const list = normalise(data).slice(0, 5);
        if (activity) activity.innerHTML = list.length
          ? list.map(item => `<li><span class="dot ok"></span><div><strong>${escapeHtml(item.name || item.symbol || item.status || item.event || 'Backend record')}</strong><small>${escapeHtml(item.updated_at || item.created_at || item.timestamp || item.createdAt || 'Live')}</small></div></li>`).join('')
          : '<li class="empty-state">No recent records.</li>';
      }
      if (status) status.textContent = 'Backend connected';
      await accountKPIs();
    } catch (error) {
      if (status) status.textContent = 'Backend partially unavailable';
      if (message) message.textContent = error.message;
      renderTable([], $('[data-enterprise-table]', page));
    }
  }

  function boot() {
    $$('[data-enterprise-page], [data-module-page]').forEach(page => genericWorkspace(page));
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true}); else boot();
})();
