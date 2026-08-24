(() => {
  'use strict';
  if (window.__algoBotLiveChart) return;
  window.__algoBotLiveChart = true;

  const $ = s => document.querySelector(s);
  let ws = null, symbol = '', points = [], reconnectTimer = null, intentionallyClosed = false, boundSelect = null;
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const money = value => Number.isFinite(Number(value)) ? Number(value).toLocaleString(undefined, { minimumFractionDigits:2, maximumFractionDigits:8 }) : 'Unavailable';
  const wsUrl = () => `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/market-data/`;
  const brokerReady = () => {
    const state = window.AlgoBotBrokerState?.get();
    return !!state?.account && ['CONNECTED', 'SYNCING', 'READY', 'DEGRADED'].includes(state.status);
  };

  function render() {
    const chart = $('#chart');
    if (!chart || points.length < 2) return;
    const width = 1000, height = 330, pad = 18, values = points.map(point => point.price), min = Math.min(...values), max = Math.max(...values), span = max - min || Math.max(Math.abs(max) * 0.0001, 1);
    const coords = points.map((point, index) => `${(pad + index / Math.max(1, points.length - 1) * (width - pad * 2)).toFixed(1)},${(height - pad - (point.price - min) / span * (height - pad * 2)).toFixed(1)}`).join(' ');
    const latest = values.at(-1), rising = latest >= values[0], stroke = rising ? '#43d19a' : '#ff6b7d', last = coords.split(' ').at(-1).split(',');
    chart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="width:100%;height:100%;display:block"><polyline points="${coords}" fill="none" stroke="${stroke}" stroke-width="2.5"></polyline><circle cx="${last[0]}" cy="${last[1]}" r="4" fill="${stroke}"></circle><text x="${width-pad}" y="${pad+2}" text-anchor="end" fill="currentColor" opacity=".7" font-size="13">LIVE ${money(latest)}</text></svg>`;
    $('#terminal-status')?.setAttribute('title', `AlgoBot live market stream · ${points.length} broker quotes`);
    $('[data-chart-loading]')?.replaceChildren(document.createTextNode(`Live broker stream · ${points.length} quotes`));
    $('[data-trend]')?.replaceChildren(document.createTextNode(rising ? 'Bullish' : 'Bearish'));
    const mean = values.reduce((a, b) => a + b, 0) / values.length, variance = values.reduce((a, b) => a + (b - mean) ** 2, 0) / values.length;
    $('[data-volatility]')?.replaceChildren(document.createTextNode(money(Math.sqrt(variance))));
    $('[data-structure]')?.replaceChildren(document.createTextNode(rising ? 'Higher-price structure' : 'Lower-price structure'));
  }

  async function loadHistory(nextSymbol) {
    if (!brokerReady()) return;
    try {
      const data = await window.AlgoBotFrontendData.request(`/api/market/ticks/history/?symbol=${encodeURIComponent(nextSymbol)}&limit=120`, {}, 5000);
      const history = list(data).map(tick => ({ price:Number(tick.quote), epoch:Number(tick.epoch) })).filter(tick => Number.isFinite(tick.price)).reverse();
      if (history.length) { points = history.slice(-120); render(); }
    } catch (_) {
      $('[data-chart-loading]')?.replaceChildren(document.createTextNode('Live market history unavailable; waiting for broker stream'));
    }
  }

  function closeSocket() { if (ws) { try { ws.close(); } catch (_) {} ws = null; } }

  function connect(nextSymbol) {
    if (!nextSymbol || document.visibilityState !== 'visible' || !brokerReady()) return;
    symbol = nextSymbol; intentionallyClosed = false; clearTimeout(reconnectTimer); closeSocket();
    try {
      ws = new WebSocket(wsUrl());
      ws.addEventListener('open', () => { if (!ws || ws.readyState !== WebSocket.OPEN) return; ws.send(JSON.stringify({ action:'subscribe', symbol })); });
      ws.addEventListener('message', event => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === 'error') { $('[data-chart-loading]')?.replaceChildren(document.createTextNode(payload.error?.message || 'Market stream error')); return; }
          const tick = payload.type === 'market.tick' ? payload : null;
          if (!tick || String(tick.symbol || symbol) !== symbol) return;
          const price = Number(tick.price);
          if (!Number.isFinite(price)) return;
          points.push({ price, epoch:Number(tick.epoch) || Date.now() / 1000 });
          points = points.slice(-120);
          $('[data-q="price"]')?.replaceChildren(document.createTextNode(money(price)));
          $('[data-q="bid"]')?.replaceChildren(document.createTextNode(money(tick.bid ?? price)));
          $('[data-q="ask"]')?.replaceChildren(document.createTextNode(money(tick.ask ?? price)));
          render();
        } catch (_) {}
      });
      ws.addEventListener('close', () => { ws = null; if (!intentionallyClosed && document.visibilityState === 'visible' && brokerReady()) { clearTimeout(reconnectTimer); reconnectTimer = setTimeout(() => connect(symbol), 3000); } });
      ws.addEventListener('error', () => $('[data-chart-loading]')?.replaceChildren(document.createTextNode('Broker market stream reconnecting…')));
    } catch (_) { reconnectTimer = setTimeout(() => connect(symbol), 3000); }
  }

  function bind(select) {
    if (boundSelect === select) return;
    boundSelect = select;
    if (select.value && brokerReady()) { loadHistory(select.value); connect(select.value); }
    select.addEventListener('change', () => { symbol = select.value; points = []; intentionallyClosed = true; closeSocket(); if (symbol && brokerReady()) { loadHistory(symbol); connect(symbol); } });
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible' && select.value && brokerReady()) connect(select.value); if (document.visibilityState !== 'visible') { intentionallyClosed = true; closeSocket(); } });
  }

  function renderDisconnected(state) {
    intentionallyClosed = true;
    closeSocket();
    points = [];
    $('[data-chart-loading]')?.replaceChildren(document.createTextNode(state?.status === 'NO_BROKER' ? 'Connect a broker to load the live chart' : 'Broker disconnected; chart stream paused'));
  }

  function start() {
    if (document.body.dataset.authenticated !== 'true' || !$('#chart')) return;
    window.AlgoBotBrokerState?.subscribe(event => {
      const state = event.detail.state;
      if (['NO_BROKER', 'DISCONNECTED'].includes(state.status)) renderDisconnected(state);
      else if (['CONNECTED', 'READY'].includes(state.status)) { const select = $('#symbol'); if (select?.value) { loadHistory(select.value); connect(select.value); } }
    });
    let attempts = 0;
    const waitForSymbol = () => {
      const select = $('#symbol');
      if (select?.value) return bind(select);
      attempts += 1;
      if (attempts < 40) setTimeout(waitForSymbol, 250);
      else $('[data-chart-loading]')?.replaceChildren(document.createTextNode('No broker market instrument available'));
    };
    waitForSymbol();
  }

  window.addEventListener('DOMContentLoaded', start, { once:true });
})();
