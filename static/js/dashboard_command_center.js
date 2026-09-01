(() => {
  'use strict';
  if (window.__algoBotCommandCenter) return;
  window.__algoBotCommandCenter = true;

  const $ = (selector) => document.querySelector(selector);
  const list = (value) => Array.isArray(value) ? value : (Array.isArray(value?.data) ? value.data : (Array.isArray(value?.results) ? value.results : []));
  const esc = (value) => { const node = document.createElement('div'); node.textContent = String(value ?? ''); return node.innerHTML; };
  const money = (value) => value == null || value === '' || Number.isNaN(Number(value)) ? 'Unavailable' : Number(value).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 8});
  const setText = (selector, value) => { const node = $(selector); if (node) node.textContent = value; };
  const setHtml = (selector, value) => { const node = $(selector); if (node) node.innerHTML = value; };
  const empty = (message) => `<div class="empty-state">${esc(message)}</div>`;

  let busy = false;
  let timer = null;
  let lastLoadedAt = null;
  const REFRESH_MS = 45000;

  function request(url, options = {}, timeout = 8000) {
    const shared = window.AlgoBotFrontendData?.request;
    if (typeof shared === 'function') return shared(url, options, timeout);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    return fetch(url, {credentials: 'same-origin', cache: 'no-store', ...options, headers: {Accept: 'application/json', ...(options.headers || {})}, signal: controller.signal})
      .then(async (response) => {
        const body = await response.text();
        let data = {};
        try { data = body ? JSON.parse(body) : {}; } catch (_) { data = {detail: body}; }
        if (!response.ok) throw Object.assign(new Error(data.detail || data.message || `Request failed (${response.status})`), {status: response.status});
        return data;
      })
      .catch((error) => { if (error?.name === 'AbortError') throw Object.assign(new Error('Request timed out'), {code: 'API_TIMEOUT'}); throw error; })
      .finally(() => clearTimeout(timeoutId));
  }

  function status(key, state, label) {
    const dot = $(`[data-status-dot="${key}"]`);
    const text = $(`[data-status="${key}"]`);
    if (dot) dot.className = `status-dot ${state || ''}`.trim();
    if (text) text.textContent = label;
  }

  function renderAccount(account, message = '') {
    if (!account) {
      ['balance','equity','available','pnl'].forEach(key => setText(`[data-kpi="${key}"]`, 'Unavailable'));
      setText('[data-kpi-state="balance"]', message || 'No authoritative broker account');
      setText('[data-kpi-state="equity"]', 'No broker equity reported');
      status('account', 'error', message || 'Broker account unavailable');
      setHtml('[data-dashboard-brokers]', `<span><b></b>${esc(message || 'No connected broker account')}</span>`);
      return;
    }
    const currency = account.currency || '';
    const pnl = account.net_profit_loss ?? account.net_pnl ?? account.profit_loss ?? account.pnl;
    const equity = account.equity ?? (pnl != null && account.balance != null ? Number(account.balance) + Number(pnl) : null);
    setText('[data-kpi="balance"]', `${currency} ${money(account.balance)}`.trim());
    setText('[data-kpi="equity"]', `${currency} ${money(equity)}`.trim());
    setText('[data-kpi="available"]', `${currency} ${money(account.free_margin ?? account.available_margin ?? account.available)}`.trim());
    setText('[data-kpi="pnl"]', pnl == null ? 'Unavailable' : `${currency} ${money(pnl)}`.trim());
    setText('[data-kpi-state="balance"]', 'Authoritative broker snapshot');
    setText('[data-kpi-state="equity"]', account.equity == null ? 'Not reported by broker' : 'Authoritative broker equity');
    const broker = account.broker?.name || account.broker_name || 'Broker';
    const id = account.account_id || account.broker_account_id || account.loginid || 'Account';
    const sync = account.last_synced_at ? new Date(account.last_synced_at).toLocaleTimeString() : 'snapshot';
    setHtml('[data-dashboard-brokers]', `<span><b></b><strong>${esc(broker)}</strong> · ${esc(id)} · CONNECTED</span><small>Broker snapshot · ${esc(sync)}</small>`);
    status('account', 'ok', 'Broker account available');
  }

  function renderRows(selector, values, renderer, fallback) {
    setHtml(selector, values.length ? values.map(renderer).join('') : empty(fallback));
  }

  function renderCollections(result) {
    const positions = result.positions.ok ? list(result.positions.value).slice(0, 8) : [];
    const orders = result.orders.ok ? list(result.orders.value).slice(0, 8) : [];
    const markets = result.markets.ok ? list(result.markets.value).slice(0, 8) : [];
    const signals = result.signals.ok ? list(result.signals.value).slice(0, 8) : [];

    renderRows('[data-dashboard-positions]', positions, item => `<div class="mini-row"><strong>${esc(item.symbol?.symbol || item.symbol || 'Market')}</strong><span>${esc(item.direction || item.side || '')}</span><b>${esc(item.profit ?? item.pnl ?? item.profit_loss ?? '—')}</b></div>`, result.positions.ok ? 'No open positions reported by the backend.' : 'Position service unavailable.');
    renderRows('[data-dashboard-orders]', orders, item => `<div class="mini-row"><strong>${esc(item.symbol?.symbol || item.symbol || 'Market')}</strong><span>${esc(item.direction || item.side || '')}</span><b>${esc(item.status || 'Unknown')}</b></div>`, result.orders.ok ? 'No orders reported by the backend.' : 'Order service unavailable.');
    renderRows('[data-dashboard-markets]', markets, item => `<div class="mini-row"><strong>${esc(item.symbol?.symbol || item.symbol?.display_name || item.display_name || item.symbol || 'Market')}</strong><span>${item.bid_price != null || item.bid != null ? `Bid ${esc(item.bid_price ?? item.bid)} · Ask ${esc(item.ask_price ?? item.ask)}` : 'Broker market catalogue'}</span><b>${esc(item.price ?? item.last_price ?? item.close ?? 'Available')}</b></div>`, result.markets.ok ? 'No market snapshot is currently available.' : 'Market data service unavailable.');
    renderRows('[data-dashboard-signals]', signals, item => `<div class="signal-row"><strong>${esc(item.symbol?.symbol || item.symbol || 'Market')} · ${esc(item.direction || item.signal || 'HOLD')}</strong><span>${esc(item.strategy?.name || item.strategy || item.market_regime || '')}</span><b>${item.confidence != null ? `${Number(item.confidence).toFixed(0)}%` : '—'}</b></div>`, result.signals.ok ? 'No recent backend signals.' : 'Signal service unavailable.');

    status('positions', result.positions.ok ? (positions.length ? 'ok' : 'warn') : 'error', result.positions.ok ? (positions.length ? 'Exposure available' : 'No open positions') : 'Position service unavailable');
    status('execution', result.orders.ok ? (orders.length ? 'ok' : 'warn') : 'error', result.orders.ok ? (orders.length ? 'Execution feed available' : 'No recent orders') : 'Order service unavailable');
    status('markets', result.markets.ok ? (markets.length ? 'ok' : 'warn') : 'error', result.markets.ok ? (markets.length ? 'Market data available' : 'No market snapshot') : 'Market data unavailable');
    status('signals', result.signals.ok ? (signals.length ? 'ok' : 'warn') : 'error', result.signals.ok ? (signals.length ? 'AI signal feed available' : 'No recent signals') : 'Signal service unavailable');

    const activity = [
      ...orders.map(item => ({label: item.symbol?.symbol || item.symbol || 'Order', meta: item.status || 'Order', time: item.updated_at || item.created_at})),
      ...signals.map(item => ({label: item.symbol?.symbol || item.symbol || 'Signal', meta: item.direction || item.signal || 'Signal', time: item.created_at || item.timestamp}))
    ].filter(item => item.time).sort((a,b) => new Date(b.time) - new Date(a.time)).slice(0, 8);
    renderRows('[data-dashboard-activity]', activity, item => `<div class="mini-row"><strong>${esc(item.label)}</strong><span>${esc(item.meta)}</span><b>${esc(new Date(item.time).toLocaleString())}</b></div>`, 'No recent backend activity.');
  }

  async function load() {
    if (busy) return;
    busy = true;
    setText('[data-dashboard-sync]', 'Refreshing authoritative snapshot…');
    document.documentElement.dataset.dashboardLoading = 'true';
    try {
      const responses = await Promise.allSettled([
        request('/api/dashboard/account_overview/', {}, 8000),
        request('/api/positions/open/', {}, 8000),
        request('/api/orders/', {}, 8000),
        request('/api/market/snapshots/all_snapshots/', {}, 8000),
        request('/api/dashboard/signals/?limit=8', {}, 8000)
      ]);
      const [account, positions, orders, markets, signals] = responses;
      if (account.status === 'fulfilled') renderAccount(account.value?.data?.account || account.value?.account || null);
      else renderAccount(null, account.reason?.code === 'API_TIMEOUT' ? 'Broker snapshot timed out' : 'Broker snapshot unavailable');
      renderCollections({
        positions: {ok: positions.status === 'fulfilled', value: positions.value, error: positions.reason},
        orders: {ok: orders.status === 'fulfilled', value: orders.value, error: orders.reason},
        markets: {ok: markets.status === 'fulfilled', value: markets.value, error: markets.reason},
        signals: {ok: signals.status === 'fulfilled', value: signals.value, error: signals.reason}
      });
      lastLoadedAt = new Date();
      setText('[data-dashboard-sync]', `Updated ${lastLoadedAt.toLocaleTimeString()} · snapshot only`);
      window.dispatchEvent(new CustomEvent('algobot:dashboard-updated', {detail: {timestamp: lastLoadedAt.toISOString()}}));
    } catch (error) {
      setText('[data-dashboard-sync]', 'Dashboard update failed · last known state retained');
      window.dispatchEvent(new CustomEvent('algobot:dashboard-error', {detail: error}));
    } finally {
      busy = false;
      document.documentElement.dataset.dashboardLoading = 'false';
      clearTimeout(timer);
      timer = setTimeout(load, REFRESH_MS);
    }
  }

  async function killSwitch() {
    if (!window.confirm('Activate the trading emergency stop? New execution should be blocked until risk controls are restored.')) return;
    const button = $('[data-dashboard-kill-switch]');
    if (button) button.disabled = true;
    try {
      await request('/api/risk/kill-switch/activate/', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({reason:'Dashboard emergency stop'})}, 8000);
      setText('[data-dashboard-sync]', `Emergency stop confirmed · ${new Date().toLocaleTimeString()}`);
      window.dispatchEvent(new CustomEvent('algobot:kill-switch-activated'));
    } catch (error) {
      setText('[data-dashboard-sync]', error?.message || 'Emergency stop request failed');
    } finally { if (button) button.disabled = false; }
  }

  function boot() {
    $('[data-dashboard-refresh]')?.addEventListener('click', load);
    $('[data-dashboard-kill-switch]')?.addEventListener('click', killSwitch);
    document.addEventListener('visibilitychange', () => { if (document.hidden) clearTimeout(timer); else { clearTimeout(timer); timer = setTimeout(load, 250); } });
    window.addEventListener('algobot:account-changed', () => { clearTimeout(timer); timer = setTimeout(load, 250); });
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true}); else boot();
})();
