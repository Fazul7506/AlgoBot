/* Resilient trading terminal recovery layer. Keeps broker/API truth authoritative. */
(() => {
  'use strict';
  if (window.__algoBotTradingTerminalRecovery) return;
  window.__algoBotTradingTerminalRecovery = true;

  const $ = (s) => document.querySelector(s);
  const data = () => window.AlgoBotFrontendData;
  const list = (v) => data()?.list(v) || [];
  const request = (url, options = {}, timeout = 10000) => data().request(url, options, timeout);
  const text = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const money = (v) => Number.isFinite(Number(v)) ? Number(v).toLocaleString(undefined, {maximumFractionDigits: 8}) : 'Unavailable';

  let accountRows = [];
  let refreshTimer = null;

  function connectedAccount() {
    return accountRows.find(a => a.is_connected) || accountRows.find(a => a.is_preferred || a.is_default) || accountRows[0] || null;
  }

  function renderAccounts(rows) {
    accountRows = list(rows).filter(a => a?.id);
    const select = $('#account');
    if (!select) return;
    const previous = select.value;
    if (!accountRows.length) {
      select.innerHTML = '<option value="">No connected broker account</option>';
      $('[data-risk-check]')?.replaceChildren(document.createTextNode('Broker account required'));
      return;
    }
    select.innerHTML = accountRows.map(a => `<option value="${text(a.id)}">${text(a.broker?.name || a.broker_name || 'Broker')} · ${text(a.broker_account_id || a.account_id || '')} · ${text(a.currency || '')}</option>`).join('');
    const chosen = accountRows.some(a => String(a.id) === previous) ? previous : String((connectedAccount() || {}).id || '');
    select.value = chosen;
    $('[data-risk-check]')?.replaceChildren(document.createTextNode(connectedAccount()?.is_connected ? 'Pre-trade checks active' : 'Broker verification required'));
  }

  async function loadAccounts() {
    try { renderAccounts(await request('/api/brokers/accounts/')); }
    catch (e) { $('[data-risk-check]')?.replaceChildren(document.createTextNode(`Broker account unavailable: ${e.message}`)); }
  }

  async function loadSymbols() {
    const select = $('#symbol');
    if (!select) return '';
    const previous = select.value;
    try {
      const rows = list(await request('/api/markets/symbols/'))
        .filter(r => r?.symbol && r.is_active !== false && r.is_tradeable !== false && r.is_tradable !== false);
      if (!rows.length) {
        select.innerHTML = '<option value="">No active broker instruments</option>';
        return '';
      }
      select.innerHTML = rows.map(r => `<option value="${text(r.symbol)}">${text(r.display_name || r.symbol)} · ${text(r.symbol)}</option>`).join('');
      const requested = new URLSearchParams(location.search).get('symbol');
      const selected = [previous, requested, rows[0].symbol].find(v => rows.some(r => r.symbol === v));
      select.value = selected || rows[0].symbol;
      return select.value;
    } catch (e) {
      select.innerHTML = `<option value="">Market catalogue unavailable: ${text(e.message)}</option>`;
      return '';
    }
  }

  function renderCapabilities(payload) {
    const timeframes = Array.isArray(payload?.timeframes) ? payload.timeframes : [];
    const select = $('#timeframe');
    const buttons = $('[data-chart-timeframes]');
    if (!timeframes.length) {
      if (select) select.innerHTML = '<option value="">No broker timeframes available</option>';
      if (buttons) buttons.innerHTML = '';
      return;
    }
    if (select) {
      const old = select.value;
      select.innerHTML = timeframes.map(tf => `<option value="${text(tf.seconds)}">${text(tf.label || tf.seconds)}</option>`).join('');
      const requested = new URLSearchParams(location.search).get('timeframe');
      select.value = timeframes.some(tf => String(tf.seconds) === requested) ? requested : (timeframes.some(tf => String(tf.seconds) === old) ? old : String(timeframes[0].seconds));
    }
    if (buttons) {
      const active = select?.value || String(timeframes[0].seconds);
      buttons.innerHTML = timeframes.map(tf => `<button type="button" data-recovery-timeframe="${text(tf.seconds)}" class="${String(tf.seconds) === active ? 'active' : ''}">${text(tf.label || tf.seconds)}</button>`).join('');
      buttons.querySelectorAll('[data-recovery-timeframe]').forEach(b => b.addEventListener('click', () => {
        buttons.querySelectorAll('button').forEach(x => x.classList.remove('active'));
        b.classList.add('active');
        if (select) select.value = b.dataset.recoveryTimeframe;
        loadChartHistory();
      }));
    }
  }

  async function loadCapabilities() {
    try { renderCapabilities(await request('/api/chart/capabilities/')); }
    catch (e) {
      try { renderCapabilities(await request('/api/market/chart/capabilities/')); }
      catch (_) {
        const select = $('#timeframe');
        if (select) select.innerHTML = `<option value="">Broker capabilities unavailable</option>`;
      }
    }
  }

  async function loadQuote() {
    const symbol = $('#symbol')?.value;
    if (!symbol) return;
    try {
      const tick = await request(`/api/market/ticks/broker/?symbol=${encodeURIComponent(symbol)}`, {}, 10000);
      const price = tick.bid ?? tick.ask ?? tick.quote ?? tick.price;
      $('[data-q="bid"]')?.replaceChildren(document.createTextNode(money(tick.bid ?? price)));
      $('[data-q="ask"]')?.replaceChildren(document.createTextNode(money(tick.ask ?? tick.quote ?? price)));
      $('[data-chart-loading]')?.replaceChildren(document.createTextNode(tick.stale ? 'Last known broker quote · stale' : 'Live broker quote'));
      return tick;
    } catch (e) {
      $('[data-q="bid"]')?.replaceChildren(document.createTextNode('Quote unavailable'));
      $('[data-q="ask"]')?.replaceChildren(document.createTextNode('Quote unavailable'));
      $('[data-chart-loading]')?.replaceChildren(document.createTextNode(`Broker quote unavailable: ${e.message}`));
    }
  }

  function drawTicks(items) {
    const chart = $('#chart');
    const points = list(items).map(x => Number(x.quote ?? x.price)).filter(Number.isFinite).reverse().slice(-120);
    if (!chart || points.length < 2) return;
    const w = 1000, h = 330, p = 18, min = Math.min(...points), max = Math.max(...points), span = max - min || Math.max(Math.abs(max) * 0.0001, 1);
    const coords = points.map((v, i) => `${(p + i / (points.length - 1) * (w - p * 2)).toFixed(1)},${(h - p - (v - min) / span * (h - p * 2)).toFixed(1)}`).join(' ');
    chart.innerHTML = `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:100%;display:block"><polyline points="${coords}" fill="none" stroke="currentColor" stroke-width="2.5"/><text x="${w-p}" y="${p+2}" text-anchor="end" fill="currentColor" opacity=".7" font-size="13">BROKER ${text(money(points.at(-1)))}</text></svg>`;
    $('[data-trend]')?.replaceChildren(document.createTextNode(points.at(-1) >= points[0] ? 'Bullish' : 'Bearish'));
    const mean = points.reduce((a,b) => a+b, 0) / points.length;
    const variance = points.reduce((a,b) => a + (b-mean) ** 2, 0) / points.length;
    $('[data-volatility]')?.replaceChildren(document.createTextNode(money(Math.sqrt(variance))));
    $('[data-structure]')?.replaceChildren(document.createTextNode('Broker tick history'));
    $('[data-chart-loading]')?.replaceChildren(document.createTextNode(`Broker tick history · ${points.length} points`));
  }

  async function loadChartHistory() {
    const symbol = $('#symbol')?.value;
    if (!symbol) return;
    const mode = document.querySelector('[data-chart-mode].active')?.dataset.chartMode || 'ticks';
    try {
      const tf = $('#timeframe')?.value || '';
      const url = `/api/chart/history/?symbol=${encodeURIComponent(symbol)}&mode=${encodeURIComponent(mode)}&limit=120${mode === 'candles' && tf ? `&granularity=${encodeURIComponent(tf)}` : ''}`;
      const payload = await request(url);
      if (mode === 'ticks') drawTicks(payload?.items || payload);
      else if (window.__algoBotLiveChart) {
        /* The existing chart renderer will consume the same authoritative history. */
        $('[data-chart-loading]')?.replaceChildren(document.createTextNode(`Broker candlestick history loaded · ${list(payload?.items || payload).length} points`));
      }
    } catch (e) {
      $('[data-chart-loading]')?.replaceChildren(document.createTextNode(`Broker chart unavailable: ${e.message}`));
    }
  }

  async function loadRecords() {
    const [positions, orders, signals] = await Promise.allSettled([
      request('/api/positions/open/'), request('/api/orders/'), request('/api/strategies/signals/')
    ]);
    const rows = (r) => r.status === 'fulfilled' ? list(r.value) : [];
    const p = rows(positions), o = rows(orders).slice(0, 8), s = rows(signals).slice(0, 8);
    const posTarget = $('[data-positions]');
    if (posTarget) posTarget.innerHTML = p.length ? p.map(x => `<div class="mini-row"><strong>${text(x.symbol)}</strong><span>${text(x.direction || x.side || '')}</span><b>${text(x.profit ?? x.pnl ?? '—')}</b></div>`).join('') : `<div class="empty-state">${positions.status === 'rejected' ? text(positions.reason?.message || 'Positions unavailable.') : 'No open positions reported by the broker.'}</div>`;
    const orderTarget = $('[data-orders]');
    if (orderTarget) orderTarget.innerHTML = o.length ? o.map(x => `<div class="mini-row"><strong>${text(x.symbol)}</strong><span>${text(x.direction || x.side || '')}</span><b>${text(x.status || '')}</b></div>`).join('') : `<div class="empty-state">${orders.status === 'rejected' ? text(orders.reason?.message || 'Orders unavailable.') : 'No orders reported by the execution API.'}</div>`;
    const signalTarget = $('[data-signals]');
    if (signalTarget) signalTarget.innerHTML = s.length ? s.map(x => `<div class="mini-row"><strong>${text(x.symbol || x.strategy || 'Signal')}</strong><span>${text(x.action || x.direction || '')}</span><b>${text(x.confidence ?? '')}</b></div>`).join('') : '<div class="empty-state">No strategy signals returned yet.</div>';
  }

  async function refreshRecovery() {
    await Promise.all([loadAccounts(), loadSymbols(), loadCapabilities()]);
    await Promise.all([loadQuote(), loadChartHistory(), loadRecords()]);
  }

  function bind() {
    $('#symbol')?.addEventListener('change', () => { loadQuote(); loadChartHistory(); });
    $('#timeframe')?.addEventListener('change', loadChartHistory);
    $('[data-action="terminal-refresh"]')?.addEventListener('click', refreshRecovery);
    const analyze = $('[data-ai-analyze]');
    analyze?.addEventListener('click', () => setTimeout(loadRecords, 1000));
  }

  function boot() {
    if (!$('.terminal-page')) return;
    bind();
    refreshRecovery();
    refreshTimer = setInterval(() => { loadQuote(); loadRecords(); }, 15000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true});
  else boot();
})();
