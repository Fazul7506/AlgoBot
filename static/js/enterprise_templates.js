(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  const json = async (url, opts = {}) => {
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
    try {
      const [overview, accounts] = await Promise.all([
        json('/api/dashboard/account_overview/'),
        json('/api/brokers/accounts/')
      ]);
      const data = overview.data || {};
      const stats = data.trading_stats || {};
      const accountsList = normalise(accounts);
      const account = accountsList.find(x => x.is_default) || accountsList[0];
      const balance = $('[data-kpi="balance"]');
      const positions = $('[data-kpi="positions"]');
      const winrate = $('[data-kpi="winrate"]');
      const pnl = $('[data-kpi="pnl"]');
      if (balance) balance.textContent = account ? `${account.currency || ''} ${money(account.balance)}`.trim() : '—';
      if (positions) positions.textContent = stats.open_trades ?? '0';
      if (winrate) winrate.textContent = pct(stats.win_rate);
      if (pnl) pnl.textContent = money(stats.total_pnl);
      const terminalAccount = $('[data-terminal-account]');
      if (terminalAccount) terminalAccount.textContent = `Account: ${account?.broker_account_id || data.account?.account_id || 'Not connected'}`;
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

  function drawCandles(canvas, candles) {
    if (!canvas || !candles?.length) return;
    const box = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(box.width, 300);
    const height = Math.max(box.height, 250);
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const data = candles.map(x => ({
      o: +(x.open ?? x.o), h: +(x.high ?? x.h), l: +(x.low ?? x.l), c: +(x.close ?? x.c)
    })).filter(x => [x.o, x.h, x.l, x.c].every(Number.isFinite));
    if (!data.length) return;
    const min = Math.min(...data.map(x => x.l));
    const max = Math.max(...data.map(x => x.h));
    const range = max - min || 1;
    const step = width / data.length;
    const bodyWidth = Math.max(2, step * 0.55);
    const y = value => height - ((value - min) / range) * height * 0.86 - height * 0.04;
    ctx.strokeStyle = 'rgba(143,164,194,.14)';
    for (let i = 1; i < 6; i++) { ctx.beginPath(); ctx.moveTo(0, height * i / 6); ctx.lineTo(width, height * i / 6); ctx.stroke(); }
    data.forEach((item, i) => {
      const x = i * step + step / 2;
      const up = item.c >= item.o;
      ctx.strokeStyle = up ? '#33d69f' : '#ff5c7a';
      ctx.fillStyle = ctx.strokeStyle;
      ctx.beginPath(); ctx.moveTo(x, y(item.h)); ctx.lineTo(x, y(item.l)); ctx.stroke();
      const top = Math.min(y(item.o), y(item.c));
      const bodyHeight = Math.max(1, Math.abs(y(item.c) - y(item.o)));
      ctx.fillRect(x - bodyWidth / 2, top, bodyWidth, bodyHeight);
    });
  }

  async function tradingTerminal(page) {
    let direction = 'BUY';
    let accountId = null;
    const symbol = $('[data-symbol]', page);
    const timeframe = $('[data-timeframe]', page);
    const strategySelect = $('[name="strategy"]', page);
    const load = async () => {
      const s = encodeURIComponent(symbol.value);
      const tf = encodeURIComponent(timeframe.value);
      try {
        const [chart, regime, snapshots, accounts, strategies] = await Promise.all([
          json(`/api/market/price-history/chart_data/?symbol=${s}&timeframe=${tf}&days=1`),
          json(`/api/market/regime/?symbol=${s}&timeframe=${tf}`),
          json(`/api/market/snapshots/?symbol=${s}`),
          json('/api/brokers/accounts/'),
          json('/api/strategies/')
        ]);
        const candles = normalise(chart.candles || chart.data?.candles || chart);
        drawCandles($('[data-candle-chart]', page), candles);
        $('.chart-overlay', page).style.display = candles.length ? 'none' : 'grid';
        const r = regime.data || regime;
        $('[data-regime]', page).textContent = r.market_regime || r.regime || '—';
        $('[data-trend]', page).textContent = r.trend_direction || r.trend || '—';
        $('[data-volatility]', page).textContent = r.volatility != null ? Number(r.volatility).toFixed(2) : '—';
        $('[data-recommended]', page).textContent = r.recommended_strategy || '—';
        $('[data-structure]', page).textContent = typeof r.structure_insight === 'string' ? r.structure_insight : (r.structure_insight?.trend || '—');
        $('[data-chart-title]', page).textContent = `${symbol.value} · ${timeframe.value}`;
        const snapshot = normalise(snapshots)[0];
        if (snapshot) {
          $('[data-bid]', page).textContent = snapshot.bid_price ?? snapshot.bid ?? snapshot.price ?? '—';
          $('[data-ask]', page).textContent = snapshot.ask_price ?? snapshot.ask ?? snapshot.price ?? '—';
        }
        const accountsList = normalise(accounts);
        const account = accountsList.find(x => x.is_default) || accountsList[0];
        accountId = account?.id || null;
        const strategiesList = normalise(strategies);
        if (strategySelect) {
          const current = strategySelect.value;
          strategySelect.innerHTML = '<option value="">Manual trade</option>';
          strategiesList.forEach(item => {
            const option = document.createElement('option');
            option.value = item.name || item.slug;
            option.textContent = `${item.name || item.slug}${item.enabled === false ? ' (disabled)' : ''}`;
            option.disabled = item.enabled === false;
            strategySelect.appendChild(option);
          });
          if (current) strategySelect.value = current;
        }
        $('[data-terminal-status]', page).textContent = account?.is_connected ? 'Ready to trade' : 'Broker account required';
        $('[data-terminal-account]', page).textContent = `Account: ${account?.broker_account_id || 'Not connected'}`;
        $('[data-risk-check]', page).textContent = account ? 'Pre-trade checks active' : 'Connect broker first';
      } catch (error) {
        $('[data-terminal-status]', page).textContent = 'Data unavailable';
        toast(error.message, 'error');
      }
      await Promise.all([loadPositions(page), loadSignals(page), loadOrders(page), accountKPIs()]);
    };

    async function loadPositions(p) {
      try {
        const rows = normalise(await json('/api/positions/open/'));
        $('[data-positions]', p).innerHTML = rows.length ? rows.map(x => `<div class="mini-row"><strong>${escapeHtml(x.symbol)}</strong><span>${escapeHtml(x.direction || '')}</span><b>${money(x.profit ?? x.pnl ?? x.profit_loss)}</b></div>`).join('') : '<div class="empty-state">No open positions.</div>';
      } catch { $('[data-positions]', p).innerHTML = '<div class="empty-state">Unable to load positions.</div>'; }
    }
    async function loadSignals(p) {
      try {
        const rows = normalise(await json(`/api/dashboard/signals/?symbol=${encodeURIComponent(symbol.value)}&limit=8`));
        $('[data-signals]', p).innerHTML = rows.length ? rows.map(x => `<div class="signal-row"><strong>${escapeHtml(x.symbol)} ${escapeHtml(x.direction || x.signal || 'HOLD')}</strong><span>${escapeHtml(x.strategy || 'Strategy')}</span><b>${pct(x.confidence)}</b></div>`).join('') : '<div class="empty-state">No recent signals.</div>';
      } catch { $('[data-signals]', p).innerHTML = '<div class="empty-state">No signals available.</div>'; }
    }
    async function loadOrders(p) {
      try {
        const rows = normalise(await json('/api/orders/')).slice(0, 8);
        $('[data-orders]', p).innerHTML = rows.length ? rows.map(x => `<div class="mini-row"><strong>${escapeHtml(x.symbol)}</strong><span>${escapeHtml(x.direction || '')}</span><b>${escapeHtml(x.status || '')}</b></div>`).join('') : '<div class="empty-state">No orders yet.</div>';
      } catch { $('[data-orders]', p).innerHTML = '<div class="empty-state">No orders yet.</div>'; }
    }

    $$('[data-direction]', page).forEach(button => button.addEventListener('click', () => {
      direction = button.dataset.direction;
      $$('[data-direction]', page).forEach(item => item.classList.toggle('active', item === button));
    }));

    $('[data-order-form]', page)?.addEventListener('submit', async event => {
      event.preventDefault();
      if (!accountId) { toast('Connect a broker account before trading.', 'error'); return; }
      const form = new FormData(event.currentTarget);
      const payload = {
        broker_account: accountId,
        symbol: symbol.value,
        direction,
        order_type: form.get('order_type'),
        stake: form.get('stake'),
        strategy: form.get('strategy') || '',
        client_request_id: `ui-${crypto.randomUUID ? crypto.randomUUID() : Date.now()}`
      };
      if (form.get('price')) payload.price = form.get('price');
      const button = $('.execute-btn', page);
      button.disabled = true;
      button.textContent = 'Submitting…';
      try {
        const result = await json('/api/orders/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
          body: JSON.stringify(payload)
        });
        const output = $('[data-order-result]', page);
        output.hidden = false;
        output.textContent = `Order ${result.id ? `#${result.id}` : ''} ${result.status || 'submitted'}.`;
        toast('Order submitted to execution engine.', 'success');
        await load();
      } catch (error) {
        toast(`Order rejected: ${error.message}`, 'error');
      } finally {
        button.disabled = false;
        button.textContent = 'Place order';
      }
    });

    $('[data-action="terminal-refresh"]', page)?.addEventListener('click', load);
    symbol?.addEventListener('change', load);
    timeframe?.addEventListener('change', load);
    load();
  }

  async function dataPage(page) {
    const id = page.dataset.dataPage;
    const map = {
      'orders-page': '/api/orders/',
      'positions-page': '/api/positions/open/',
      'signals-page': '/api/dashboard/signals/?limit=100',
      'portfolio-page': '/api/portfolio/'
    };
    const url = map[id];
    if (!url) return;
    const table = $('[data-page-table]', page);
    const status = $('[data-page-status]', page);
    const updated = $('[data-page-updated]', page);
    const risk = $('[data-page-risk]', page);
    async function load() {
      try {
        const data = await json(url);
        const rows = normalise(data);
        if ($('[data-record-count]', page)) $('[data-record-count]', page).textContent = rows.length;
        if (status) status.textContent = 'Live';
        if (updated) updated.textContent = new Date().toLocaleTimeString();
        if (risk) risk.textContent = 'Controlled';
        renderTable(data, table, 100);
      } catch (error) {
        if (status) status.textContent = 'Unavailable';
        const tbody = $('tbody', table);
        if (tbody) tbody.innerHTML = `<tr class="empty-row"><td>${escapeHtml(error.message)}</td></tr>`;
      }
    }
    $('[data-page-search]', page)?.addEventListener('input', event => {
      $$('tbody tr', page).forEach(row => { row.hidden = !row.textContent.toLowerCase().includes(event.target.value.toLowerCase()); });
    });
    load();
  }

  function theme() {
    $('[data-theme-toggle]')?.addEventListener('click', () => {
      document.documentElement.dataset.theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    });
  }
  function shell() {
    const sidebar = $('[data-app-sidebar]');
    const backdrop = $('[data-sidebar-backdrop]');
    const open = () => { sidebar?.classList.add('is-open'); document.body.classList.add('sidebar-open'); if (backdrop) backdrop.hidden = false; };
    const close = () => { sidebar?.classList.remove('is-open'); document.body.classList.remove('sidebar-open'); if (backdrop) backdrop.hidden = true; };
    $('[data-sidebar-toggle]')?.addEventListener('click', () => document.body.classList.toggle('sidebar-collapsed'));
    $('[data-sidebar-open]')?.addEventListener('click', open);
    $('[data-sidebar-close]')?.addEventListener('click', close);
    backdrop?.addEventListener('click', close);
    document.addEventListener('keydown', event => { if (event.key === 'Escape') { close(); closeAccountMenu(); } });
    $$('.app-sidebar nav a').forEach(link => link.addEventListener('click', close));
  }

  function closeAccountMenu() {
    const trigger = $('[data-account-trigger]');
    const dropdown = $('[data-account-dropdown]');
    if (dropdown) dropdown.hidden = true;
    trigger?.setAttribute('aria-expanded', 'false');
  }

  function accountMenu() {
    const menu = $('[data-account-menu]');
    const trigger = $('[data-account-trigger]');
    const dropdown = $('[data-account-dropdown]');
    trigger?.addEventListener('click', event => {
      event.stopPropagation();
      const isOpen = dropdown && !dropdown.hidden;
      if (dropdown) dropdown.hidden = isOpen;
      trigger.setAttribute('aria-expanded', String(!isOpen));
    });
    document.addEventListener('click', event => { if (menu && !menu.contains(event.target)) closeAccountMenu(); });
    $('[data-logout-form]')?.addEventListener('submit', async event => {
      event.preventDefault();
      try {
        await json('/logout/', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() }, body: '{}' });
      } finally {
        window.location.assign('/login/');
      }
    });
  }

  async function init() {
    theme();
    shell();
    accountMenu();
    $$('.enterprise-page').forEach(page => {
      genericWorkspace(page);
      $('[data-action="refresh"]', page)?.addEventListener('click', () => genericWorkspace(page));
      $('[data-action="reload-records"]', page)?.addEventListener('click', () => genericWorkspace(page));
      $('[data-action="export-csv"]', page)?.addEventListener('click', () => toast('Use the module export endpoint for a signed report.', 'info'));
      $('[data-action="kill-switch"]', page)?.addEventListener('click', async () => {
        if (!confirm('Activate the trading kill switch? New execution should be blocked until it is deactivated.')) return;
        try {
          await json('/api/risk/kill-switch/activate/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
            body: JSON.stringify({ reason: 'Manual activation from AlgoBot UI' })
          });
          toast('Kill switch activated.', 'success');
          await genericWorkspace(page);
        } catch (error) { toast(`Kill switch failed: ${error.message}`, 'error'); }
      });
    });
    const terminal = $('.terminal-page');
    if (terminal) tradingTerminal(terminal);
    $$('.data-page').forEach(dataPage);
  }

  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', init) : init();
})();
