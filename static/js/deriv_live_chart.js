(() => {
  const WS_URL = 'wss://api.derivws.com/trading/v1/options/ws/public';
  const $ = (s) => document.querySelector(s);
  let ws = null;
  let symbol = '';
  let points = [];
  let reconnectTimer = null;
  let intentionallyClosed = false;

  const list = value => Array.isArray(value) ? value : (Array.isArray(value?.results) ? value.results : []);
  const money = value => Number.isFinite(Number(value)) ? Number(value).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 8}) : 'Unavailable';

  function render() {
    const chart = $('#chart');
    if (!chart || points.length < 2) return;
    const width = 1000, height = 330, pad = 18;
    const values = points.map(p => p.price);
    const min = Math.min(...values), max = Math.max(...values);
    const span = max - min || Math.max(Math.abs(max) * 0.0001, 1);
    const coords = points.map((p, i) => `${(pad + i / Math.max(1, points.length - 1) * (width - pad * 2)).toFixed(1)},${(height - pad - (p.price - min) / span * (height - pad * 2)).toFixed(1)}`).join(' ');
    const latest = values.at(-1);
    const rising = latest >= values[0];
    const stroke = rising ? '#43d19a' : '#ff6b7d';
    const last = coords.split(' ').at(-1).split(',');
    chart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="width:100%;height:100%;display:block"><polyline points="${coords}" fill="none" stroke="${stroke}" stroke-width="2.5"></polyline><circle cx="${last[0]}" cy="${last[1]}" r="4" fill="${stroke}"></circle><text x="${width-pad}" y="${pad+2}" text-anchor="end" fill="currentColor" opacity=".7" font-size="13">LIVE ${money(latest)}</text></svg>`;
    $('#terminal-status')?.setAttribute('title', `Live broker stream · ${points.length} quotes`);
    $('[data-chart-loading]')?.replaceChildren(document.createTextNode(`Live broker stream · ${points.length} quotes`));
    $('[data-trend]')?.replaceChildren(document.createTextNode(rising ? 'Bullish' : 'Bearish'));
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const variance = values.reduce((a, b) => a + (b - mean) ** 2, 0) / values.length;
    $('[data-volatility]')?.replaceChildren(document.createTextNode(money(Math.sqrt(variance))));
    $('[data-structure]')?.replaceChildren(document.createTextNode(rising ? 'Higher-price structure' : 'Lower-price structure'));
  }

  async function loadHistory(nextSymbol) {
    try {
      const response = await fetch(`/api/market/ticks/history/?symbol=${encodeURIComponent(nextSymbol)}&limit=120`, {credentials: 'same-origin', headers: {Accept: 'application/json'}});
      if (!response.ok) return;
      const data = await response.json();
      const history = list(data).map(t => ({price: Number(t.quote), epoch: Number(t.epoch)})).filter(t => Number.isFinite(t.price)).reverse();
      if (history.length) { points = history.slice(-120); render(); }
    } catch (_) {}
  }

  function closeSocket() {
    if (ws) {
      try { ws.close(); } catch (_) {}
      ws = null;
    }
  }

  function connect(nextSymbol) {
    if (!nextSymbol || document.visibilityState !== 'visible') return;
    symbol = nextSymbol;
    intentionallyClosed = false;
    closeSocket();
    try {
      ws = new WebSocket(WS_URL);
      ws.addEventListener('open', () => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        ws.send(JSON.stringify({ticks: symbol, subscribe: 1}));
        $('#terminal-status')?.setAttribute('title', `Live broker stream · ${symbol}`);
      });
      ws.addEventListener('message', event => {
        try {
          const payload = JSON.parse(event.data);
          const tick = payload.tick;
          if (!tick || String(tick.symbol || symbol) !== symbol) return;
          const price = Number(tick.quote);
          if (!Number.isFinite(price)) return;
          points.push({price, epoch: Number(tick.epoch) || Date.now() / 1000});
          points = points.slice(-120);
          $('[data-q="price"]')?.replaceChildren(document.createTextNode(money(price)));
          $('[data-q="bid"]')?.replaceChildren(document.createTextNode(money(tick.bid ?? price)));
          $('[data-q="ask"]')?.replaceChildren(document.createTextNode(money(tick.ask ?? price)));
          render();
        } catch (_) {}
      });
      ws.addEventListener('close', () => {
        ws = null;
        if (!intentionallyClosed && document.visibilityState === 'visible') {
          clearTimeout(reconnectTimer);
          reconnectTimer = setTimeout(() => connect(symbol), 3000);
        }
      });
      ws.addEventListener('error', () => {});
    } catch (_) {
      clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(() => connect(symbol), 3000);
    }
  }

  function bind(select) {
    const startSymbol = select.value;
    if (startSymbol) { loadHistory(startSymbol); connect(startSymbol); }
    select.addEventListener('change', () => {
      symbol = select.value;
      points = [];
      intentionallyClosed = true;
      closeSocket();
      if (symbol) { loadHistory(symbol); connect(symbol); }
    });
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && select.value) connect(select.value);
      if (document.visibilityState !== 'visible') { intentionallyClosed = true; closeSocket(); }
    });
  }

  function start() {
    if (document.body.dataset.authenticated !== 'true' || !$('#chart')) return;
    let attempts = 0;
    const waitForSymbol = () => {
      const select = $('#symbol');
      if (select?.value) return bind(select);
      attempts += 1;
      if (attempts < 40) setTimeout(waitForSymbol, 250);
    };
    waitForSymbol();
  }

  window.addEventListener('DOMContentLoaded', start, {once: true});
})();
