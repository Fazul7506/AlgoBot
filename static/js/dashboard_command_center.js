(() => {
  'use strict';
  if (window.__algoBotCommandCenter) return;
  window.__algoBotCommandCenter = true;

  const $ = (selector) => document.querySelector(selector);
  const list = (value) => Array.isArray(value) ? value : (Array.isArray(value?.data) ? value.data : (Array.isArray(value?.results) ? value.results : []));
  const esc = (value) => { const node = document.createElement('div'); node.textContent = String(value ?? ''); return node.innerHTML; };
  const money = (value, currency = 'USD') => { if (value == null || value === '' || !Number.isFinite(Number(value))) return 'Unavailable'; if (typeof window.AlgoBotMoney?.format === 'function') return window.AlgoBotMoney.format(value, currency); return `${String(currency || 'USD').toUpperCase() === 'USD' ? '$' : `${String(currency || '').toUpperCase()} `}${Number(value).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:8})}`; };
  const setText = (selector, value) => { const node = $(selector); if (node) node.textContent = value; };
  const setHtml = (selector, value) => { const node = $(selector); if (node) node.innerHTML = value; };
  const empty = (message) => `<div class="empty-state">${esc(message)}</div>`;

  let busy = false;
  let timer = null;
  let lastLoadedAt = null;
  let selectedAccountId = null;
  let loadSeq = 0;
  const REFRESH_MS = 45000;
  const ACCOUNT_TIMEOUT_MS = 15000;
  const SNAPSHOT_KEY = 'algobot:dashboard:last-verified-account:v2';

  function request(url, options = {}, timeout = 8000) {
    const shared = window.AlgoBotFrontendData?.request;
    if (typeof shared !== 'function') {
      return Promise.reject(new Error('Canonical frontend transport is not ready.'));
    }
    // The API's active-account authority is the server-side Django session.
    // Preserve that cookie on Dashboard reads while keeping the canonical transport.
    return shared(url, {credentials: 'include', ...options}, timeout);
  }

  function status(key, state, label) {
    const dot = $(`[data-status-dot="${key}"]`);
    const text = $(`[data-status="${key}"]`);
    if (dot) dot.className = `status-dot ${state || ''}`.trim();
    if (text) text.textContent = label;
  }

  function currentAccountId() {
    if (selectedAccountId != null) return String(selectedAccountId);
    const account = window.AlgoBotBrokerState?.get?.()?.account;
    return account?.id != null ? String(account.id) : null;
  }

  function readLastAccountSnapshot() {
    try {
      const raw = sessionStorage.getItem(SNAPSHOT_KEY);
      const value = raw ? JSON.parse(raw) : null;
      if (!value || !value.account) return null;
      const requestedId = currentAccountId();
      if (!requestedId || value.account.id == null || String(value.account.id) !== requestedId) return null;
      return value;
    } catch (_) { return null; }
  }
  function writeLastAccountSnapshot(account) {
    if (!account) return;
    try { sessionStorage.setItem(SNAPSHOT_KEY, JSON.stringify({at: Date.now(), account})); } catch (_) {}
  }

  function renderAccount(account, message = '', persistSnapshot = true) {
    if (!account) {
      ['balance','equity','available','pnl'].forEach(key => setText(`[data-kpi="${key}"]`, 'Unavailable'));
      setText('[data-kpi-state="balance"]', message || 'No authoritative broker account');
      setText('[data-kpi-state="equity"]', 'No broker equity reported');
      status('account', 'error', message || 'Broker account unavailable');
      setHtml('[data-dashboard-brokers]', `<span><b></b>${esc(message || 'No connected broker account')}</span>`);
      return;
    }
    selectedAccountId = account.id != null ? String(account.id) : selectedAccountId;
    const currency = account.currency || '';
    const pnl = account.net_profit_loss ?? account.net_pnl ?? account.profit_loss ?? account.pnl;
    const equity = account.equity ?? (pnl != null && account.balance != null ? Number(account.balance) + Number(pnl) : null);
    setText('[data-kpi="balance"]', money(account.balance, currency));
    setText('[data-kpi="equity"]', money(equity, currency));
    setText('[data-kpi="available"]', money(account.free_margin ?? account.available_margin ?? account.available, currency));
    setText('[data-kpi="pnl"]', pnl == null ? 'Unavailable' : money(pnl, currency));
    const freshness = String(account.data_freshness || 'unknown').toLowerCase();
    const connected = account.is_connected === true;
    const snapshotLabel = freshness === 'fresh' ? 'Fresh broker snapshot' : freshness === 'stale' ? 'Stale broker snapshot' : 'Broker snapshot freshness unknown';
    setText('[data-kpi-state="balance"]', freshness === 'fresh' ? 'Authoritative broker snapshot' : snapshotLabel);
    setText('[data-kpi-state="equity"]', account.equity == null ? 'Not reported by broker' : (freshness === 'fresh' ? 'Authoritative broker equity' : snapshotLabel));
    const broker = typeof account.broker === 'string' ? account.broker : (account.broker?.name || account.broker_name || 'Broker');
    const id = account.account_id || account.broker_account_id || account.loginid || 'Account';
    const sync = account.last_synced_at ? new Date(account.last_synced_at).toLocaleTimeString() : 'not verified';
    const connectionLabel = connected ? 'CONNECTED' : 'CONNECTION UNCONFIRMED';
    setHtml('[data-dashboard-brokers]', `<span><b></b><strong>${esc(broker)}</strong> · ${esc(id)} · ${esc(connectionLabel)}</span><small>${esc(snapshotLabel)} · ${esc(sync)}</small>`);
    const accountState = connected && freshness === 'fresh' ? 'ok' : (freshness === 'stale' || freshness === 'unknown' || !connected ? 'warn' : 'error');
    const accountStatus = !connected ? 'Broker connection unconfirmed' : freshness === 'fresh' ? 'Broker account synchronized' : freshness === 'stale' ? 'Broker snapshot is stale' : 'Broker snapshot freshness unknown';
    status('account', accountState, accountStatus);
    // Only cache a snapshot confirmed fresh by the broker and connection layer.
    if (persistSnapshot && connected && freshness === 'fresh') writeLastAccountSnapshot(account);
  }

  function renderRows(selector, values, renderer, fallback) {
    setHtml(selector, values.length ? values.map(renderer).join('') : empty(fallback));
  }

  function snapshotAge(value) {
    const timestamp = value == null ? NaN : Date.parse(value);
    if (!Number.isFinite(timestamp)) return 'freshness unavailable';
    const seconds = Math.floor((Date.now() - timestamp) / 1000);
    if (seconds < 0) return 'timestamp ahead of local clock';
    if (seconds < 60) return `updated ${seconds}s ago`;
    if (seconds < 3600) return `updated ${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `updated ${Math.floor(seconds / 3600)}h ago`;
    return `updated ${Math.floor(seconds / 86400)}d ago`;
  }

  function renderCollections(result) {
    const positions = result.positions.ok ? list(result.positions.value).slice(0, 8) : [];
    const orders = result.orders.ok ? list(result.orders.value).slice(0, 8) : [];
    const markets = result.markets.ok ? list(result.markets.value).slice(0, 8) : [];
    const signals = result.signals.ok ? list(result.signals.value).slice(0, 8) : [];
    const marketsTimestamped = markets.some(item => Number.isFinite(Date.parse(item.timestamp)));
    const positionsStale = result.positions.ok && (result.positions.value?.status === 'stale' || result.positions.value?.source === 'broker_cache');
    const ordersStale = result.orders.ok && (result.orders.value?.status === 'stale' || result.orders.value?.source === 'broker_cache');

    renderRows('[data-dashboard-positions]', positions, item => `<div class="mini-row"><strong>${esc(item.symbol?.symbol || item.symbol || 'Market')}</strong><span>${esc(item.direction || item.side || '')}</span><b>${esc(item.profit ?? item.pnl ?? item.profit_loss ?? '—')}</b></div>`, result.positions.ok ? 'No open positions reported by the backend.' : 'Position service unavailable.');
    renderRows('[data-dashboard-orders]', orders, item => `<div class="mini-row"><strong>${esc(item.symbol?.symbol || item.symbol || 'Market')}</strong><span>${esc(item.direction || item.side || '')}</span><b>${esc(item.status || 'Unknown')}</b></div>`, result.orders.ok ? 'No orders reported by the backend.' : 'Order service unavailable.');
    renderRows('[data-dashboard-markets]', markets, item => `<div class="mini-row"><strong>${esc(item.symbol?.symbol || item.symbol?.display_name || item.display_name || item.symbol || 'Market')}</strong><span>${item.bid_price != null || item.bid != null ? `Bid ${esc(item.bid_price ?? item.bid ?? 'Unavailable')} · Ask ${esc(item.ask_price ?? item.ask ?? 'Unavailable')}` : 'Broker market catalogue'} · ${esc(snapshotAge(item.timestamp))}</span><b>${esc(item.price ?? item.last_price ?? item.close ?? 'Available')}</b></div>`, result.markets.ok ? 'No market snapshot is currently available.' : 'Market data service unavailable.');
    renderRows('[data-dashboard-signals]', signals, item => `<div class="signal-row"><strong>${esc(item.symbol?.symbol || item.symbol || 'Market')} · ${esc(item.direction || item.signal || 'HOLD')}</strong><span>${esc(item.strategy?.name || item.strategy || item.market_regime || '')}</span><b>${item.confidence != null && Number.isFinite(Number(item.confidence)) ? `${Number(item.confidence).toFixed(0)}%` : '—'}</b></div>`, result.signals.ok ? 'No recent backend signals.' : 'Signal service unavailable.');

    const positionSync = result.positions.value?.meta?.last_synced_at || result.positions.value?.meta?.last_synced || null;
    const orderSync = result.orders.value?.meta?.last_synced_at || result.orders.value?.meta?.last_synced || null;
    status('positions', !result.positions.ok ? 'error' : (positions.length && !positionsStale ? 'ok' : 'warn'),
      !result.positions.ok ? 'Position service unavailable' : positionsStale ? `Cached exposure · ${snapshotAge(positionSync)}` : positions.length ? 'Exposure available' : 'No open positions');
    status('execution', !result.orders.ok ? 'error' : (orders.length && !ordersStale ? 'ok' : 'warn'),
      !result.orders.ok ? 'Order service unavailable' : ordersStale ? `Cached orders · ${snapshotAge(orderSync)}` : orders.length ? 'Execution feed available' : 'No recent orders');
    status('markets', result.markets.ok ? (markets.length && marketsTimestamped ? 'ok' : 'warn') : 'error', result.markets.ok ? (markets.length && marketsTimestamped ? 'Market snapshot timestamps available' : markets.length ? 'Market data returned · freshness unknown' : 'No market snapshot') : 'Market data unavailable');
    status('signals', result.signals.ok ? (signals.length ? 'ok' : 'warn') : 'error', result.signals.ok ? (signals.length ? 'AI signal feed available' : 'No recent signals') : 'Signal service unavailable');

    const activity = [
      ...orders.map(item => ({label: item.symbol?.symbol || item.symbol || 'Order', meta: item.status || 'Order', time: item.updated_at || item.created_at})),
      ...signals.map(item => ({label: item.symbol?.symbol || item.symbol || 'Signal', meta: item.direction || item.signal || 'Signal', time: item.created_at || item.timestamp}))
    ].filter(item => item.time && Number.isFinite(Date.parse(item.time))).sort((a,b) => Date.parse(b.time) - Date.parse(a.time)).slice(0, 8);
    renderRows('[data-dashboard-activity]', activity, item => `<div class="mini-row"><strong>${esc(item.label)}</strong><span>${esc(item.meta)}</span><b>${esc(new Date(item.time).toLocaleString())}</b></div>`, 'No recent backend activity.');
  }

  async function load() {
    const seq = ++loadSeq;
    const active = window.AlgoBotBrokerState?.get?.()?.account;
    const requestedAccountId = active?.id != null ? String(active.id) : null;
    // Clear the previous account identity when no account is selected; otherwise
    // its cached snapshot could survive a disconnect and be shown on a timeout.
    selectedAccountId = requestedAccountId;
    busy = true;
    setText('[data-dashboard-sync]', 'Refreshing authoritative snapshot…');
    document.documentElement.dataset.dashboardLoading = 'true';
    try {
      const responses = await Promise.allSettled([
        request('/api/dashboard/account_overview/', {}, ACCOUNT_TIMEOUT_MS),
        request('/api/positions/open/', {}, 8000),
        request('/api/dashboard/trade_history/?days=30&limit=8', {}, 8000),
        request('/api/market/snapshots/all_snapshots/', {}, 8000),
        request('/api/dashboard/signals/?limit=8', {}, 8000)
      ]);
      const currentId = window.AlgoBotBrokerState?.get?.()?.account?.id;
      if (seq !== loadSeq || (requestedAccountId != null && currentId != null && String(currentId) !== requestedAccountId)) return;
      const [account, positions, orders, markets, signals] = responses;
      const accountPayload = account.status === 'fulfilled'
        ? (account.value?.data?.account || account.value?.account || null)
        : null;
      // Never paint an account response that belongs to a different selection.
      // Internal account IDs are compared only when both sides expose one.
      if (requestedAccountId != null && accountPayload && (accountPayload.id == null || String(accountPayload.id) !== requestedAccountId)) {
        renderAccount(null, 'Account changed during refresh · retrying');
        setText('[data-dashboard-sync]', 'Account selection changed · refreshing');
        loadSeq += 1; // Prevent this request's finally block from replacing the fast retry.
        timer = setTimeout(load, 250);
        return;
      }
      if (account.status === 'fulfilled') renderAccount(accountPayload);
      else if (account.reason?.code === 'API_TIMEOUT') {
        const stale = readLastAccountSnapshot();
        if (stale?.account) {
          renderAccount(stale.account, '', false);
          const verifiedAt = stale.account.last_synced_at || stale.at;
          setText('[data-kpi-state="balance"]', `Last verified broker snapshot · refresh timed out${verifiedAt ? ` · ${new Date(verifiedAt).toLocaleTimeString()}` : ''}`);
          status('account', 'warn', 'Broker refresh timed out · last verified snapshot shown');
        } else renderAccount(null, 'Broker snapshot timed out · refresh again');
      } else renderAccount(null, 'Broker snapshot unavailable');
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
      if (seq !== loadSeq) return;
      setText('[data-dashboard-sync]', 'Dashboard update failed · last known state retained');
      window.dispatchEvent(new CustomEvent('algobot:dashboard-error', {detail: error}));
    } finally {
      if (seq === loadSeq) {
        busy = false;
        document.documentElement.dataset.dashboardLoading = 'false';
        clearTimeout(timer);
        timer = setTimeout(load, REFRESH_MS);
      }
    }
  }

  function boot() {
    $('[data-dashboard-refresh]')?.addEventListener('click', load);
    document.addEventListener('visibilitychange', () => { if (document.hidden) clearTimeout(timer); else { clearTimeout(timer); timer = setTimeout(load, 250); } });
    const accountChanged = (event) => { selectedAccountId = event.detail?.id != null ? String(event.detail.id) : null; loadSeq += 1; busy = false; clearTimeout(timer); timer = setTimeout(load, 250); };
    window.addEventListener('algobot:account-changed', accountChanged);
    window.addEventListener('algobot:account-synced', accountChanged);
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true}); else boot();
})();
