(() => {
  'use strict';
  if (window.__algoBotDashboardV2) return;
  window.__algoBotDashboardV2 = true;

  const $ = (s) => document.querySelector(s);
  const list = (v) => Array.isArray(v) ? v : (Array.isArray(v?.results) ? v.results : (Array.isArray(v?.data) ? v.data : []));
  const esc = (v) => { const d = document.createElement('div'); d.textContent = String(v ?? ''); return d.innerHTML; };
  const money = (v) => v == null || v === '' || Number.isNaN(Number(v)) ? 'Unavailable' : Number(v).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 8});

  let loading = false;
  let refreshTimer = null;
  let liveAccount = null;
  let socket = null;
  let reconnectTimer = null;
  let reconnects = 0;
  let streamState = 'starting';
  const MAX_RECONNECTS = 3;
  const contracts = new Map();

  const text = (s, v) => { const n = $(s); if (n) n.textContent = v; };
  const html = (s, v) => { const n = $(s); if (n) n.innerHTML = v; };
  const empty = (m) => `<div class="empty-state">${esc(m)}</div>`;
  const sync = (m) => text('[data-dashboard-sync]', m);

  function request(url, options = {}, timeout = 7000) {
    const shared = window.AlgoBotFrontendData?.request;
    if (typeof shared === 'function') {
      return Promise.race([
        shared(url, options, timeout),
        new Promise((_, reject) => setTimeout(() => reject(Object.assign(new Error('Request timed out'), {code: 'API_TIMEOUT'})), timeout))
      ]);
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    return fetch(url, {credentials: 'same-origin', cache: 'no-store', ...options, headers: {Accept: 'application/json', ...(options.headers || {})}, signal: controller.signal})
      .then(async (r) => {
        const body = await r.text(); let data = {};
        try { data = body ? JSON.parse(body) : {}; } catch (_) { data = {detail: body}; }
        if (!r.ok) throw Object.assign(new Error(data.detail || data.message || `Request failed (${r.status})`), {status: r.status, payload: data});
        return data;
      })
      .catch((e) => { if (e?.name === 'AbortError') throw Object.assign(new Error('Request timed out'), {code: 'API_TIMEOUT'}); throw e; })
      .finally(() => clearTimeout(timer));
  }

  function renderAccount(account, error = '') {
    if (!account) {
      text('[data-kpi="balance"]', 'Unavailable'); text('[data-kpi="equity"]', 'Unavailable'); text('[data-kpi="available"]', 'Unavailable'); text('[data-kpi="pnl"]', 'Unavailable');
      text('[data-kpi-state="balance"]', error || 'No connected broker account'); text('[data-kpi-state="equity"]', 'Broker account data unavailable'); return;
    }
    liveAccount = {...(liveAccount || {}), ...account};
    const c = liveAccount.currency || '';
    const pnl = liveAccount.net_profit_loss ?? liveAccount.net_pnl ?? liveAccount.profit_loss ?? liveAccount.pnl;
    const equity = liveAccount.equity ?? (pnl != null && liveAccount.balance != null ? Number(liveAccount.balance) + Number(pnl) : null);
    text('[data-kpi="balance"]', `${c} ${money(liveAccount.balance)}`.trim());
    text('[data-kpi="equity"]', `${c} ${money(equity)}`.trim());
    text('[data-kpi="available"]', `${c} ${money(liveAccount.free_margin ?? liveAccount.available_margin ?? liveAccount.available)}`.trim());
    text('[data-kpi="pnl"]', pnl == null ? 'Unavailable' : `${c} ${money(pnl)}`.trim());
    text('[data-kpi-state="balance"]', liveAccount.is_connected === false ? 'Last known broker data' : 'Broker balance');
    text('[data-kpi-state="equity"]', equity == null ? 'Waiting for broker equity or open-contract P/L' : (liveAccount.equity == null ? 'Derived from balance + open-contract P/L' : 'Broker equity'));
  }

  function renderBroker(account, error = '') {
    if (!account) { html('[data-dashboard-brokers]', empty(error || 'No connected broker account')); return; }
    const broker = account.broker?.name || account.broker_name || 'Deriv';
    const id = account.broker_account_id || account.account_id || account.loginid || 'Account';
    const connected = account.is_connected !== false;
    let state = connected ? 'LIVE' : 'DEGRADED';
    if (connected && streamState === 'fallback') state = 'CONNECTED · REST SNAPSHOT';
    if (connected && streamState === 'connecting') state = 'CONNECTED · LIVE FEED RETRYING';
    html('[data-dashboard-brokers]', `<span><b></b>${esc(broker)} · ${esc(id)} · ${esc(state)}</span>`);
  }

  function rows(selector, data, render, fallback) { html(selector, data.length ? data.map(render).join('') : empty(fallback)); }

  function setFallback(message) {
    streamState = 'fallback';
    if (socket) { try { socket.close(); } catch (_) {} }
    socket = null;
    sync(message || `Snapshot · ${new Date().toLocaleTimeString()}`);
    if (liveAccount) renderBroker(liveAccount);
  }

  function scheduleReconnect() {
    if (reconnectTimer || reconnects >= MAX_RECONNECTS || document.hidden) return;
    const delay = Math.min(30000, 1000 * Math.pow(2, reconnects - 1));
    reconnectTimer = setTimeout(() => { reconnectTimer = null; connectStream(); }, delay);
  }

  function connectStream() {
    if (document.hidden || socket || document.body.dataset.authenticated !== 'true') return;
    if (!('WebSocket' in window)) return setFallback('Live feed unsupported · using latest broker snapshot');
    if (reconnects >= MAX_RECONNECTS) return setFallback('Live feed unavailable · using latest broker snapshot');
    reconnects += 1;
    streamState = 'connecting';
    renderBroker(liveAccount);
    sync(`Connecting live feed… (${reconnects}/${MAX_RECONNECTS})`);
    try { socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/portfolio/`); }
    catch (_) { socket = null; return reconnects >= MAX_RECONNECTS ? setFallback('Live feed unavailable · using latest broker snapshot') : scheduleReconnect(); }

    socket.onopen = () => { reconnects = 0; streamState = 'live'; sync(`Live · ${new Date().toLocaleTimeString()}`); renderBroker(liveAccount); };
    socket.onmessage = (event) => {
      let m; try { m = JSON.parse(event.data); } catch (_) { return; }
      if (m.type === 'account.balance') renderAccount({...liveAccount, balance: m.balance, currency: m.currency});
      if (m.type === 'portfolio.update') {
        if (Array.isArray(m.contracts)) {
          contracts.clear(); m.contracts.forEach(c => { if (c?.contract_id != null) contracts.set(String(c.contract_id), c); });
          rows('[data-dashboard-positions]', [...contracts.values()], c => `<div class="mini-row"><strong>${esc(c.symbol || 'Market')}</strong><span>${esc(c.contract_type || '')}</span><b>${esc(c.profit ?? '—')}</b></div>`, 'No open positions reported by the connected broker.');
        }
        const patch = {net_profit_loss: m.unrealized_pnl};
        if (liveAccount?.balance != null && m.unrealized_pnl != null) patch.equity = Number(liveAccount.balance) + Number(m.unrealized_pnl);
        renderAccount({...liveAccount, ...patch, is_connected: true});
        sync(`Live · ${new Date().toLocaleTimeString()}`);
      }
      if (m.type === 'portfolio.contract' && m.contract?.contract_id != null) {
        const c = m.contract, id = String(c.contract_id);
        if (c.is_sold || c.status === 'sold' || c.status === 'closed') contracts.delete(id); else contracts.set(id, {...contracts.get(id), ...c});
        rows('[data-dashboard-positions]', [...contracts.values()], x => `<div class="mini-row"><strong>${esc(x.symbol || 'Market')}</strong><span>${esc(x.contract_type || '')}</span><b>${esc(x.profit ?? '—')}</b></div>`, 'No open positions reported by the connected broker.');
      }
      if (m.type === 'portfolio.error') setFallback('Broker live feed degraded · using latest snapshot');
    };
    socket.onerror = () => { try { socket?.close(); } catch (_) {} };
    socket.onclose = () => {
      socket = null;
      if (streamState !== 'fallback' && reconnects >= MAX_RECONNECTS) setFallback('Live feed unavailable · using latest broker snapshot');
      else if (streamState !== 'fallback') scheduleReconnect();
    };
  }

  async function loadAccount() {
    try {
      const accounts = list(await request('/api/brokers/accounts/', {}, 6000));
      const account = accounts.find(a => a.is_preferred || a.is_default) || accounts[0] || null;
      if (account) { renderAccount(account); renderBroker(account); window.AlgoBotBrokerState?.setAccount(account, 'dashboard-account-loaded'); }
      else { renderAccount(null, 'No connected broker account returned by the backend'); renderBroker(null, 'No connected broker account returned by the backend'); }
      return account;
    } catch (e) {
      const msg = e?.code === 'API_TIMEOUT' ? 'Broker account request timed out' : (e?.message || 'Broker account request failed');
      renderAccount(null, msg); renderBroker(null, msg); return null;
    }
  }

  async function loadCollections() {
    const reqs = {positions: request('/api/positions/open/', {}, 6000), orders: request('/api/orders/', {}, 6000), markets: request('/api/market/snapshots/all_snapshots/', {}, 6000), signals: request('/api/dashboard/signals/?limit=8', {}, 6000), symbols: request('/api/market/symbols/?page_size=8', {}, 6000)};
    const out = {};
    await Promise.all(Object.entries(reqs).map(async ([k, p]) => { try { out[k] = {ok: true, value: await p}; } catch (e) { out[k] = {ok: false, error: e}; } }));
    return out;
  }

  function renderCollections(r) {
    const positions = r.positions?.ok ? list(r.positions.value).slice(0, 8) : [];
    const orders = r.orders?.ok ? list(r.orders.value).slice(0, 8) : [];
    const markets = r.markets?.ok ? list(r.markets.value).slice(0, 8) : [];
    const symbols = r.symbols?.ok ? list(r.symbols.value).slice(0, 8) : [];
    const signals = r.signals?.ok ? list(r.signals.value).slice(0, 8) : [];
    rows('[data-dashboard-positions]', positions, x => `<div class="mini-row"><strong>${esc(x.symbol?.symbol || x.symbol || 'Market')}</strong><span>${esc(x.direction || x.side || '')}</span><b>${esc(x.profit ?? x.pnl ?? x.profit_loss ?? '—')}</b></div>`, r.positions?.error?.code === 'API_TIMEOUT' ? 'Positions request timed out' : 'No open positions reported by the backend.');
    rows('[data-dashboard-orders]', orders, x => `<div class="mini-row"><strong>${esc(x.symbol?.symbol || x.symbol || 'Market')}</strong><span>${esc(x.direction || x.side || '')}</span><b>${esc(x.status || 'Unknown')}</b></div>`, r.orders?.error?.code === 'API_TIMEOUT' ? 'Orders request timed out' : 'No orders reported by the backend.');
    rows('[data-dashboard-markets]', markets.length ? markets : symbols, x => `<div class="mini-row"><strong>${esc(x.symbol?.symbol || x.symbol?.display_name || x.display_name || x.symbol || 'Market')}</strong><span>${x.bid_price != null || x.bid != null ? `Bid ${esc(x.bid_price ?? x.bid)} · Ask ${esc(x.ask_price ?? x.ask)}` : 'Broker market catalogue'}</span><b>${esc(x.price ?? x.last_price ?? x.close ?? 'Available')}</b></div>`, r.markets?.error?.code === 'API_TIMEOUT' ? 'Market data request timed out' : 'No live market records reported by the backend.');
    rows('[data-dashboard-signals]', signals, x => `<div class="signal-row"><strong>${esc(x.symbol?.symbol || x.symbol || 'Market')} ${esc(x.direction || x.signal || 'HOLD')}</strong><span>${esc(x.strategy?.name || x.strategy || x.market_regime || '')}</span><b>${x.confidence != null ? `${Number(x.confidence).toFixed(0)}%` : '—'}</b></div>`, r.signals?.error?.code === 'API_TIMEOUT' ? 'Signals request timed out' : 'No recent backend signals reported.');
    const activity = [...orders.map(x => ({label:x.symbol?.symbol || x.symbol || 'Order', meta:x.status || 'Order', time:x.updated_at || x.created_at})), ...signals.map(x => ({label:x.symbol?.symbol || x.symbol || 'Signal', meta:x.direction || x.signal || 'Signal', time:x.created_at || x.timestamp}))].sort((a,b) => new Date(b.time || 0) - new Date(a.time || 0)).slice(0, 8);
    rows('[data-dashboard-activity]', activity, x => `<div class="mini-row"><strong>${esc(x.label)}</strong><span>${esc(x.meta || '')}</span><b>${esc(x.time ? new Date(x.time).toLocaleString() : '')}</b></div>`, 'No recent backend activity.');
    if (liveAccount?.balance != null && positions.length === 0 && (liveAccount.equity == null || liveAccount.equity === 0)) { liveAccount.equity = Number(liveAccount.balance); renderAccount(liveAccount); }
  }

  async function load() {
    if (loading) return;
    loading = true; sync('Updating dashboard…');
    const account = loadAccount();
    try { renderCollections(await loadCollections()); }
    catch (e) { const msg = e?.message || 'Dashboard backend request failed'; ['[data-dashboard-positions]','[data-dashboard-orders]','[data-dashboard-markets]','[data-dashboard-signals]','[data-dashboard-activity]'].forEach(s => html(s, empty(msg))); }
    finally { await account; loading = false; if (!document.hidden) refreshTimer = setTimeout(load, 60000); connectStream(); if (streamState === 'fallback') sync(`Snapshot · ${new Date().toLocaleTimeString()}`); }
  }

  async function killSwitch() {
    const account = window.AlgoBotBrokerState?.get?.()?.account;
    if (!account) return alert('Connect a broker account before using the kill switch.');
    if (!confirm('Activate the trading kill switch? This is an emergency stop.')) return;
    const button = $('[data-dashboard-kill-switch]'); if (button) button.disabled = true;
    try { await request('/api/risk/kill-switch/activate/', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({reason:'Dashboard emergency stop'})}, 7000); window.dispatchEvent(new CustomEvent('algobot:kill-switch-activated')); alert('Kill switch activation confirmed by the backend.'); }
    catch (e) { alert(e?.message || 'Kill switch activation failed.'); }
    finally { if (button) button.disabled = false; }
  }

  function boot() {
    $('[data-dashboard-refresh]')?.addEventListener('click', load);
    $('[data-dashboard-kill-switch]')?.addEventListener('click', killSwitch);
    document.addEventListener('visibilitychange', () => { if (document.hidden) { clearTimeout(refreshTimer); clearTimeout(reconnectTimer); reconnectTimer = null; } else { if (!loading) load(); if (streamState !== 'live') connectStream(); } });
    window.addEventListener('algobot:account-synced', e => { if (e.detail) { renderAccount(e.detail); renderBroker(e.detail); } connectStream(); });
    window.addEventListener('algobot:account-changed', e => { if (e.detail) { liveAccount = e.detail; renderAccount(e.detail); renderBroker(e.detail); } if (!loading) load(); });
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true}); else boot();
})();
