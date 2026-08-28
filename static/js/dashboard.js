(() => {
  'use strict';
  if (window.__algoBotDashboard) return;
  window.__algoBotDashboard = true;

  const $ = selector => document.querySelector(selector);
  const list = value => Array.isArray(value) ? value : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));
  const esc = value => String(value ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[c]));
  const money = value => value == null || value === '' || Number.isNaN(Number(value)) ? 'Unavailable' : Number(value).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:8});

  let loading = false;
  let refreshTimer = null;
  let refreshGeneration = 0;
  let portfolioSocket = null;
  let portfolioReconnectTimer = null;
  let portfolioReconnectAttempt = 0;
  let liveAccount = null;
  const liveContracts = new Map();

  function setText(selector, value) { const node = $(selector); if (node) node.textContent = value; }
  function setHtml(selector, html) { const node = $(selector); if (node) node.innerHTML = html; }
  function empty(message) { return `<div class="empty-state">${esc(message)}</div>`; }

  function timeoutRequest(url, options = {}, timeoutMs = 7000) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    return fetch(url, {credentials:'same-origin', cache:'no-store', ...options, headers:{Accept:'application/json', ...(options.headers || {})}, signal:controller.signal})
      .then(async response => {
        const text = await response.text(); let payload = {};
        try { payload = text ? JSON.parse(text) : {}; } catch (_) { payload = {detail:text}; }
        if (!response.ok) { const error = new Error(payload.detail || payload.message || `Request failed (${response.status})`); error.status = response.status; error.payload = payload; throw error; }
        return payload;
      })
      .catch(error => { if (error?.name === 'AbortError') { const e = new Error('Request timed out'); e.code = 'API_TIMEOUT'; throw e; } throw error; })
      .finally(() => window.clearTimeout(timer));
  }

  function api(url, options = {}, timeoutMs = 7000) {
    const shared = window.AlgoBotFrontendData?.request;
    if (typeof shared === 'function') return Promise.race([shared(url, options, timeoutMs), new Promise((_, reject) => window.setTimeout(() => reject(Object.assign(new Error('Request timed out'), {code:'API_TIMEOUT'})), timeoutMs))]);
    return timeoutRequest(url, options, timeoutMs);
  }

  function renderAccount(account, errorMessage = '') {
    if (!account) {
      setText('[data-kpi="balance"]', 'Unavailable'); setText('[data-kpi="equity"]', 'Unavailable'); setText('[data-kpi="available"]', 'Unavailable'); setText('[data-kpi="pnl"]', 'Unavailable');
      setText('[data-kpi-state="balance"]', errorMessage || 'No connected broker account'); setText('[data-kpi-state="equity"]', 'Broker account data unavailable'); return;
    }
    liveAccount = {...(liveAccount || {}), ...account};
    const currency = liveAccount.currency || '';
    const pnl = liveAccount.net_profit_loss ?? liveAccount.net_pnl ?? liveAccount.profit_loss ?? liveAccount.pnl;
    setText('[data-kpi="balance"]', `${currency} ${money(liveAccount.balance)}`.trim());
    setText('[data-kpi="equity"]', `${currency} ${money(liveAccount.equity)}`.trim());
    setText('[data-kpi="available"]', `${currency} ${money(liveAccount.free_margin ?? liveAccount.available_margin ?? liveAccount.available)}`.trim());
    setText('[data-kpi="pnl"]', pnl == null ? 'Unavailable' : `${currency} ${money(pnl)}`.trim());
    setText('[data-kpi-state="balance"]', liveAccount.is_connected === false ? 'Last known broker data' : 'Live broker balance');
    setText('[data-kpi-state="equity"]', liveAccount.equity == null ? 'Deriv does not expose a native equity field; shown when derivable from open contracts' : 'Live broker equity');
  }

  function renderBroker(account, errorMessage = '') {
    if (!account) { setHtml('[data-dashboard-brokers]', empty(errorMessage || 'No connected broker account')); return; }
    const broker = account.broker?.name || account.broker_name || 'Deriv';
    const id = account.broker_account_id || account.account_id || account.loginid || 'Account';
    const status = account.is_connected === false ? 'DEGRADED' : 'LIVE';
    setHtml('[data-dashboard-brokers]', `<span><b></b>${esc(broker)} · ${esc(id)} · ${status}</span>`);
  }

  function renderRows(selector, rows, renderer, fallback) { setHtml(selector, rows.length ? rows.map(renderer).join('') : empty(fallback)); }

  function renderContracts(contracts) {
    const rows = Array.from(contracts.values()).filter(x => x && x.status !== 'sold' && x.status !== 'closed');
    renderRows('[data-dashboard-positions]', rows,
      x => `<div class="mini-row"><strong>${esc(x.symbol || 'Market')}</strong><span>${esc(x.contract_type || '')}</span><b>${esc(x.profit ?? '—')}</b></div>`,
      'No open positions reported by the connected broker.');
  }

  function mergeLiveAccount(patch) {
    if (!liveAccount) liveAccount = {};
    liveAccount = {...liveAccount, ...patch, is_connected:true};
    renderAccount(liveAccount);
    renderBroker(liveAccount);
    window.AlgoBotBrokerState?.setAccount(liveAccount, 'broker-realtime-update');
    window.dispatchEvent(new CustomEvent('algobot:broker-realtime-update', {detail:liveAccount}));
  }

  function wsUrl(path) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}${path}`;
  }

  function schedulePortfolioReconnect() {
    if (portfolioReconnectTimer) return;
    const delay = Math.min(30000, 1000 * Math.pow(2, Math.min(portfolioReconnectAttempt++, 5)));
    portfolioReconnectTimer = window.setTimeout(() => { portfolioReconnectTimer = null; connectPortfolioStream(); }, delay);
  }

  function connectPortfolioStream() {
    if (document.body.dataset.authenticated !== 'true' || portfolioSocket) return;
    try { portfolioSocket = new WebSocket(wsUrl('/ws/portfolio/')); }
    catch (_) { portfolioSocket = null; schedulePortfolioReconnect(); return; }

    portfolioSocket.onopen = () => {
      portfolioReconnectAttempt = 0;
      setText('[data-dashboard-sync]', `Live · ${new Date().toLocaleTimeString()}`);
      window.dispatchEvent(new CustomEvent('algobot:portfolio-stream-connected'));
    };
    portfolioSocket.onmessage = event => {
      let message; try { message = JSON.parse(event.data); } catch (_) { return; }
      const type = message.type;
      if (type === 'account.balance') {
        mergeLiveAccount({balance: message.balance, currency: message.currency});
      } else if (type === 'portfolio.update') {
        if (Array.isArray(message.contracts)) {
          liveContracts.clear(); message.contracts.forEach(contract => { if (contract?.contract_id != null) liveContracts.set(String(contract.contract_id), contract); });
          renderContracts(liveContracts);
        }
        const pnl = message.unrealized_pnl;
        const patch = {net_profit_loss: pnl};
        if (liveAccount?.balance != null && pnl != null) patch.equity = Number(liveAccount.balance) + Number(pnl);
        mergeLiveAccount(patch);
        setText('[data-dashboard-sync]', `Live · ${new Date().toLocaleTimeString()}`);
      } else if (type === 'portfolio.contract') {
        const contract = message.contract || {};
        if (contract.contract_id != null) {
          const id = String(contract.contract_id);
          if (contract.is_sold || contract.status === 'sold' || contract.status === 'closed') liveContracts.delete(id);
          else liveContracts.set(id, {...liveContracts.get(id), ...contract});
          renderContracts(liveContracts);
        }
        if (message.unrealized_pnl != null) {
          const patch = {net_profit_loss: message.unrealized_pnl};
          if (liveAccount?.balance != null) patch.equity = Number(liveAccount.balance) + Number(message.unrealized_pnl);
          mergeLiveAccount(patch);
        }
        setText('[data-dashboard-sync]', `Live · ${new Date().toLocaleTimeString()}`);
      } else if (type === 'portfolio.error') {
        setText('[data-dashboard-sync]', 'Broker stream degraded');
      }
    };
    portfolioSocket.onerror = () => { setText('[data-dashboard-sync]', 'Broker stream reconnecting…'); };
    portfolioSocket.onclose = () => { portfolioSocket = null; schedulePortfolioReconnect(); };
  }

  async function loadAccount() {
    try {
      const accounts = list(await api('/api/brokers/accounts/', {}, 6000));
      const account = accounts.find(a => a.is_preferred || a.is_default) || accounts[0] || null;
      if (account) {
        renderAccount(account); renderBroker(account); window.AlgoBotBrokerState?.setAccount(account, 'dashboard-account-loaded');
      } else { renderAccount(null, 'No connected broker account returned by the backend'); renderBroker(null, 'No connected broker account returned by the backend'); }
      return account;
    } catch (error) {
      const message = error?.code === 'API_TIMEOUT' ? 'Broker account request timed out' : (error?.message || 'Broker account request failed');
      renderAccount(null, message); renderBroker(null, message); return null;
    }
  }

  async function loadCollections() {
    const requests = {
      positions: api('/api/positions/open/', {}, 6000), orders: api('/api/orders/', {}, 6000),
      markets: api('/api/market/snapshots/all_snapshots/', {}, 6000), signals: api('/api/dashboard/signals/?limit=8', {}, 6000),
      symbols: api('/api/market/symbols/?page_size=8', {}, 6000),
    };
    const entries = await Promise.all(Object.entries(requests).map(async ([key, promise]) => { try { return [key, {ok:true, value:await promise}]; } catch (error) { return [key, {ok:false, error}]; } }));
    return Object.fromEntries(entries);
  }

  function renderCollections(result) {
    const positions = result.positions?.ok ? list(result.positions.value).slice(0, 8) : [];
    const orders = result.orders?.ok ? list(result.orders.value).slice(0, 8) : [];
    const markets = result.markets?.ok ? list(result.markets.value).slice(0, 8) : [];
    const symbols = result.symbols?.ok ? list(result.symbols.value).slice(0, 8) : [];
    const signals = result.signals?.ok ? list(result.signals.value).slice(0, 8) : [];
    const marketRows = markets.length ? markets : symbols;
    if (!liveContracts.size) renderRows('[data-dashboard-positions]', positions, x => `<div class="mini-row"><strong>${esc(x.symbol?.symbol || x.symbol || 'Market')}</strong><span>${esc(x.direction || x.side || '')}</span><b>${esc(x.profit ?? x.pnl ?? x.profit_loss ?? '—')}</b></div>`, result.positions?.error?.code === 'API_TIMEOUT' ? 'Positions request timed out' : 'No open positions reported by the backend.');
    renderRows('[data-dashboard-orders]', orders, x => `<div class="mini-row"><strong>${esc(x.symbol?.symbol || x.symbol || 'Market')}</strong><span>${esc(x.direction || x.side || '')}</span><b>${esc(x.status || 'Unknown')}</b></div>`, result.orders?.error?.code === 'API_TIMEOUT' ? 'Orders request timed out' : 'No orders reported by the backend.');
    renderRows('[data-dashboard-markets]', marketRows, x => `<div class="mini-row"><strong>${esc(x.symbol?.symbol || x.symbol?.display_name || x.display_name || x.symbol || 'Market')}</strong><span>${x.bid_price != null || x.bid != null ? `Bid ${esc(x.bid_price ?? x.bid)} · Ask ${esc(x.ask_price ?? x.ask)}` : 'Broker market catalogue'}</span><b>${esc(x.price ?? x.last_price ?? x.close ?? 'Available')}</b></div>`, result.markets?.error?.code === 'API_TIMEOUT' ? 'Market data request timed out' : 'No live market records reported by the backend.');
    renderRows('[data-dashboard-signals]', signals, x => `<div class="signal-row"><strong>${esc(x.symbol?.symbol || x.symbol || 'Market')} ${esc(x.direction || x.signal || 'HOLD')}</strong><span>${esc(x.strategy?.name || x.strategy || x.market_regime || '')}</span><b>${x.confidence != null ? Number(x.confidence).toFixed(0) + '%' : '—'}</b></div>`, result.signals?.error?.code === 'API_TIMEOUT' ? 'Signals request timed out' : 'No recent backend signals reported.');
    const activity = [...orders.map(x => ({label:x.symbol?.symbol || x.symbol || 'Order', meta:x.status || 'Order', time:x.updated_at || x.created_at})), ...signals.map(x => ({label:x.symbol?.symbol || x.symbol || 'Signal', meta:x.direction || x.signal || 'Signal', time:x.created_at || x.timestamp}))].sort((a,b) => new Date(b.time || 0) - new Date(a.time || 0)).slice(0, 8);
    renderRows('[data-dashboard-activity]', activity, x => `<div class="mini-row"><strong>${esc(x.label)}</strong><span>${esc(x.meta || '')}</span><b>${esc(x.time ? new Date(x.time).toLocaleString() : '')}</b></div>`, 'No recent backend activity.');
  }

  async function load() {
    if (loading) return;
    loading = true; const generation = ++refreshGeneration; if (refreshTimer) window.clearTimeout(refreshTimer);
    const accountPromise = loadAccount();
    try { const result = await loadCollections(); if (generation === refreshGeneration) renderCollections(result); }
    catch (error) { const message = error?.message || 'Dashboard backend request failed'; ['[data-dashboard-positions]','[data-dashboard-orders]','[data-dashboard-markets]','[data-dashboard-signals]','[data-dashboard-activity]'].forEach(selector => setHtml(selector, empty(message))); }
    finally {
      await accountPromise; loading = false;
      if (!document.hidden) refreshTimer = window.setTimeout(load, 60000);
      connectPortfolioStream();
    }
  }

  async function activateKillSwitch() {
    const account = window.AlgoBotBrokerState?.get?.()?.account;
    if (!account) { window.alert('Connect a broker account before using the kill switch.'); return; }
    if (!window.confirm('Activate the trading kill switch? This is an emergency stop.')) return;
    const button = $('[data-dashboard-kill-switch]'); if (button) button.disabled = true;
    try { await api('/api/risk/kill-switch/activate/', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({reason:'Dashboard emergency stop'})}, 7000); window.dispatchEvent(new CustomEvent('algobot:kill-switch-activated')); window.alert('Kill switch activation confirmed by the backend.'); }
    catch (error) { window.alert(error?.message || 'Kill switch activation failed.'); }
    finally { if (button) button.disabled = false; }
  }

  function boot() {
    $('[data-dashboard-refresh]')?.addEventListener('click', load);
    $('[data-dashboard-kill-switch]')?.addEventListener('click', activateKillSwitch);
    document.addEventListener('visibilitychange', () => { if (document.hidden) window.clearTimeout(refreshTimer); else { if (!loading) load(); connectPortfolioStream(); } });
    window.addEventListener('algobot:account-synced', event => { if (event.detail) { renderAccount(event.detail); renderBroker(event.detail); } connectPortfolioStream(); });
    window.addEventListener('algobot:account-changed', event => { if (event.detail) { liveAccount = event.detail; renderAccount(event.detail); renderBroker(event.detail); } if (!loading) load(); });
    connectPortfolioStream();
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true}); else boot();
})();
