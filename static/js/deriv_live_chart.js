(() => {
  'use strict';
  if (window.__algoBotLiveChart) return;
  window.__algoBotLiveChart = true;

  const $ = s => document.querySelector(s);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const money = value => Number.isFinite(Number(value)) ? Number(value).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 8}) : 'Unavailable';
  const safe = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const wsUrl = () => `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/market-data/`;
  const brokerReady = () => {
    const state = window.AlgoBotBrokerState?.get();
    return !!state?.account && ['CONNECTED','SYNCING','READY','DEGRADED'].includes(state.status);
  };
  let ws = null, symbol = '', mode = 'ticks', points = [], candles = [], capabilities = null, reconnectTimer = null, intentionallyClosed = false;

  function renderTicks() {
    const chart = $('#chart'); if (!chart || points.length < 2) return;
    const width = 1000, height = 330, pad = 18, values = points.map(p => p.price), min = Math.min(...values), max = Math.max(...values), span = max - min || Math.max(Math.abs(max) * 0.0001, 1);
    const coords = points.map((p, i) => `${(pad + i / Math.max(1, points.length - 1) * (width - pad * 2)).toFixed(1)},${(height - pad - (p.price - min) / span * (height - pad * 2)).toFixed(1)}`).join(' ');
    const latest = values.at(-1), rising = latest >= values[0], stroke = rising ? '#43d19a' : '#ff6b7d';
    chart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="width:100%;height:100%;display:block"><polyline points="${coords}" fill="none" stroke="${stroke}" stroke-width="2.5"></polyline><text x="${width-pad}" y="${pad+2}" text-anchor="end" fill="currentColor" opacity=".7" font-size="13">LIVE ${safe(money(latest))}</text></svg>`;
    updateInsights(values, 'Tick stream');
  }

  function renderCandles() {
    const chart = $('#chart'); if (!chart || candles.length < 1) return;
    const width = 1000, height = 330, pad = 18;
    const highs = candles.map(c => Number(c.high)), lows = candles.map(c => Number(c.low));
    const max = Math.max(...highs), min = Math.min(...lows), span = max - min || 1;
    const xStep = (width - pad * 2) / Math.max(1, candles.length);
    const bodyW = Math.max(2, Math.min(14, xStep * .62));
    const y = value => height - pad - (Number(value) - min) / span * (height - pad * 2);
    const parts = candles.map((c, i) => {
      const x = pad + i * xStep + xStep / 2, open = Number(c.open), close = Number(c.close), high = Number(c.high), low = Number(c.low), up = close >= open;
      const bodyTop = y(Math.max(open, close)), bodyHeight = Math.max(1, Math.abs(y(open) - y(close)));
      const stroke = up ? '#43d19a' : '#ff6b7d';
      return `<line x1="${x.toFixed(1)}" y1="${y(high).toFixed(1)}" x2="${x.toFixed(1)}" y2="${y(low).toFixed(1)}" stroke="${stroke}" stroke-width="1.5"/><rect x="${(x-bodyW/2).toFixed(1)}" y="${bodyTop.toFixed(1)}" width="${bodyW.toFixed(1)}" height="${bodyHeight.toFixed(1)}" fill="${stroke}" opacity=".82"/>`;
    }).join('');
    chart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="width:100%;height:100%;display:block">${parts}</svg>`;
    updateInsights(candles.map(c => Number(c.close)), 'Broker candlestick stream');
  }

  function updateInsights(values, structure) {
    if (!values.length) return;
    const latest = values.at(-1), first = values[0], rising = latest >= first;
    $('#terminal-status')?.setAttribute('title', `Live ${structure} · ${values.length} broker points`);
    $('[data-chart-loading]')?.replaceChildren(document.createTextNode(`Live broker data · ${values.length} points`));
    $('[data-trend]')?.replaceChildren(document.createTextNode(rising ? 'Bullish' : 'Bearish'));
    const mean = values.reduce((a,b) => a+b, 0) / values.length;
    const variance = values.reduce((a,b) => a + (b-mean) ** 2, 0) / values.length;
    $('[data-volatility]')?.replaceChildren(document.createTextNode(money(Math.sqrt(variance))));
    $('[data-structure]')?.replaceChildren(document.createTextNode(structure));
  }

  async function request(url) {
    return window.AlgoBotFrontendData.request(url, {}, 10000);
  }

  function renderCapabilities(data) {
    capabilities = data || {modes: [], timeframes: []};
    const select = $('#timeframe');
    const container = $('[data-chart-timeframes]');
    const timeframes = Array.isArray(capabilities.timeframes) ? capabilities.timeframes : [];
    if (select) {
      select.innerHTML = timeframes.length ? timeframes.map(tf => `<option value="${safe(tf.seconds)}">${safe(tf.label)}</option>`).join('') : '<option value="">No broker timeframes available</option>';
    }
    if (container) {
      container.innerHTML = timeframes.map((tf, i) => `<button type="button" data-broker-timeframe="${safe(tf.seconds)}" class="${i === 0 ? 'active' : ''}">${safe(tf.label)}</button>`).join('');
      container.querySelectorAll('[data-broker-timeframe]').forEach(button => button.addEventListener('click', () => {
        container.querySelectorAll('[data-broker-timeframe]').forEach(b => b.classList.remove('active')); button.classList.add('active');
        if (select) select.value = button.dataset.brokerTimeframe;
        if (mode === 'candles') loadHistory();
      }));
    }
  }

  async function loadCapabilities() {
    if (!brokerReady()) return;
    try { renderCapabilities(await request('/api/market/chart/capabilities/')); }
    catch (_) { $('[data-chart-loading]')?.replaceChildren(document.createTextNode('Broker chart capabilities unavailable')); }
  }

  async function loadHistory() {
    if (!brokerReady() || !symbol) return;
    try {
      const timeframe = $('#timeframe')?.value || '';
      const url = mode === 'candles'
        ? `/api/market/chart/history/?symbol=${encodeURIComponent(symbol)}&mode=candles&granularity=${encodeURIComponent(timeframe)}&limit=120`
        : `/api/market/chart/history/?symbol=${encodeURIComponent(symbol)}&mode=ticks&limit=120`;
      const data = await request(url);
      if (mode === 'candles') {
        candles = list(data.items).map(c => ({epoch:Number(c.epoch), open:Number(c.open), high:Number(c.high), low:Number(c.low), close:Number(c.close)})).filter(c => [c.open,c.high,c.low,c.close].every(Number.isFinite)).reverse();
        points = []; renderCandles();
      } else {
        points = list(data.items).map(t => ({price:Number(t.quote), epoch:Number(t.epoch)})).filter(p => Number.isFinite(p.price)).reverse().slice(-120);
        candles = []; renderTicks();
      }
    } catch (error) { $('[data-chart-loading]')?.replaceChildren(document.createTextNode(error.message || 'Live broker chart history unavailable')); }
  }

  function closeSocket() { if (ws) { try { ws.close(); } catch (_) {} ws = null; } }

  function connect(nextSymbol) {
    if (!nextSymbol || document.visibilityState !== 'visible' || !brokerReady()) return;
    symbol = nextSymbol; intentionallyClosed = false; clearTimeout(reconnectTimer); closeSocket();
    try {
      ws = new WebSocket(wsUrl());
      ws.addEventListener('open', () => ws?.readyState === WebSocket.OPEN && ws.send(JSON.stringify({action:'subscribe', symbol})));
      ws.addEventListener('message', event => {
        try {
          const payload = JSON.parse(event.data);
          const tick = payload.type === 'market.tick' ? payload : null;
          if (!tick || String(tick.symbol || symbol) !== symbol) return;
          const price = Number(tick.price); if (!Number.isFinite(price)) return;
          $('[data-q="bid"]')?.replaceChildren(document.createTextNode(money(tick.bid ?? price)));
          $('[data-q="ask"]')?.replaceChildren(document.createTextNode(money(tick.ask ?? price)));
          if (mode === 'ticks') { points.push({price, epoch:Number(tick.epoch) || Date.now()/1000}); points = points.slice(-120); renderTicks(); }
          else loadHistory();
        } catch (_) {}
      });
      ws.addEventListener('close', () => { ws = null; if (!intentionallyClosed && document.visibilityState === 'visible' && brokerReady()) reconnectTimer = setTimeout(() => connect(symbol), 3000); });
      ws.addEventListener('error', () => $('[data-chart-loading]')?.replaceChildren(document.createTextNode('Broker market stream reconnecting…')));
    } catch (_) { reconnectTimer = setTimeout(() => connect(symbol), 3000); }
  }

  function setMode(nextMode) {
    mode = nextMode;
    document.querySelectorAll('[data-chart-mode]').forEach(button => button.classList.toggle('active', button.dataset.chartMode === mode));
    const container = $('[data-chart-timeframes]'); if (container) container.style.display = mode === 'candles' ? '' : 'none';
    loadHistory();
  }

  function bind() {
    const select = $('#symbol'); if (!select) return;
    if (select.dataset.chartBound === 'true') return; select.dataset.chartBound = 'true';
    select.addEventListener('change', () => { symbol = select.value; points = []; candles = []; closeSocket(); if (symbol && brokerReady()) { loadHistory(); connect(symbol); } });
    $('#timeframe')?.addEventListener('change', () => mode === 'candles' && loadHistory());
    document.querySelectorAll('[data-chart-mode]').forEach(button => button.addEventListener('click', () => setMode(button.dataset.chartMode)));
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible' && select.value && brokerReady()) { connect(select.value); loadHistory(); } else if (document.visibilityState !== 'visible') { intentionallyClosed = true; closeSocket(); } });
  }

  function renderDisconnected(state) { intentionallyClosed = true; closeSocket(); points=[]; candles=[]; $('[data-chart-loading]')?.replaceChildren(document.createTextNode(state?.status === 'NO_BROKER' ? 'Connect a broker to load the live chart' : 'Broker disconnected; chart stream paused')); }

  async function start() {
    if (document.body.dataset.authenticated !== 'true' || !$('#chart')) return;
    window.AlgoBotBrokerState?.subscribe(event => { const state = event.detail.state; if (['NO_BROKER','DISCONNECTED'].includes(state.status)) renderDisconnected(state); else if (['CONNECTED','READY','SYNCING'].includes(state.status)) { const select=$('#symbol'); if (select?.value) { loadHistory(); connect(select.value); } } });
    bind();
    let attempts=0;
    const waitForSymbol = async () => {
      const select=$('#symbol');
      if (select?.value) { symbol=select.value; await loadCapabilities(); await loadHistory(); connect(symbol); return; }
      attempts++; if (attempts < 40) setTimeout(waitForSymbol,250); else $('[data-chart-loading]')?.replaceChildren(document.createTextNode('No broker market instrument available'));
    };
    waitForSymbol();
  }

  window.addEventListener('DOMContentLoaded', start, {once:true});
})();
