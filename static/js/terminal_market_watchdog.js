/* Authoritative public Deriv tick watchdog for the Trading Terminal. */
(() => {
  'use strict';
  if (window.__algoBotTerminalMarketWatchdog) return;
  window.__algoBotTerminalMarketWatchdog = true;

  const $ = s => document.querySelector(s);
  const WS = 'wss://api.derivws.com/trading/v1/options/ws/public';
  let ws = null;
  let activeSymbol = '';
  let reconnectTimer = null;
  let healthTimer = null;
  let stopped = false;
  let lastTickAt = 0;
  let socketStartedAt = 0;

  const fmt = value => Number.isFinite(Number(value))
    ? Number(value).toLocaleString(undefined, {maximumFractionDigits: 8})
    : 'Unavailable';

  function setState(state, detail) {
    if (state !== 'live') {
      $('[data-q="bid"]')?.replaceChildren(document.createTextNode('Unavailable'));
      $('[data-q="ask"]')?.replaceChildren(document.createTextNode('Unavailable'));
    }
    const root = $('.terminal-page');
    if (root) {
      root.dataset.marketDataState = state;
      root.dispatchEvent(new CustomEvent('algobot:market-data-state', {detail: {state, detail}}));
    }
    const panel = $('[data-market-health]');
    if (panel) {
      panel.dataset.state = state;
      panel.querySelector('[data-market-health-state]')?.replaceChildren(document.createTextNode(String(state).toUpperCase()));
      panel.querySelector('[data-market-health-detail]')?.replaceChildren(document.createTextNode(String(detail || '')));
    }
  }

  function ensurePanel() {
    const toolbar = $('.terminal-toolbar');
    if (!toolbar) return;
    if ($('[data-market-health]')) return;
    const panel = document.createElement('div');
    panel.className = 'market-health';
    panel.dataset.marketHealth = '';
    panel.innerHTML = '<span class="market-health-dot" aria-hidden="true"></span><span><strong data-market-health-state>CHECKING</strong><small data-market-health-detail>Connecting to Deriv market stream…</small></span>';
    toolbar.appendChild(panel);
  }

  function paintQuote(quote, epoch) {
    if (quote == null || quote === '') return;
    const value = Number(quote);
    if (!Number.isFinite(value)) return;
    const now = Date.now();
    const parsedEpoch = epoch == null || epoch === '' ? null : Number(epoch);
    if (parsedEpoch !== null && (!Number.isFinite(parsedEpoch) || parsedEpoch <= 0 || parsedEpoch > now / 1000 + 5)) return;
    lastTickAt = now;
    const text = fmt(value);
    // A public tick is a last-traded quote, not a broker bid/ask order book.
    $('[data-q="bid"]')?.replaceChildren(document.createTextNode('Unavailable'));
    $('[data-q="ask"]')?.replaceChildren(document.createTextNode(text));
    setState('live', `live Deriv quote · ${parsedEpoch ? new Date(parsedEpoch * 1000).toLocaleTimeString() : 'updated just now'}`);
    window.dispatchEvent(new CustomEvent('algobot:market-watchdog-tick', {detail: {symbol: activeSymbol, quote: value, epoch: parsedEpoch || Math.floor(now / 1000)}}));
  }

  function closeSocket() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    const previous = ws;
    ws = null;
    socketStartedAt = 0;
    try { previous?.close(); } catch (_) {}
  }

  function scheduleReconnect() {
    if (stopped || !activeSymbol || document.visibilityState !== 'visible' || reconnectTimer) return;
    setState('stale', 'Deriv quote stream disconnected; reconnecting…');
    reconnectTimer = setTimeout(() => { reconnectTimer = null; connect(activeSymbol); }, 1000);
  }

  function connect(symbol) {
    const normalized = String(symbol || '').trim();
    if (!normalized || stopped || document.visibilityState !== 'visible') return;
    activeSymbol = normalized;
    closeSocket();
    lastTickAt = 0;
    socketStartedAt = Date.now();
    setState('waiting', `Connecting to Deriv ticks for ${normalized}…`);
    let connection;
    try { connection = new WebSocket(WS); ws = connection; }
    catch (_) { scheduleReconnect(); return; }
    connection.onopen = () => {
      if (ws !== connection) return;
      try {
        connection.send(JSON.stringify({ticks: normalized, subscribe: 1, req_id: Date.now()}));
        setState('waiting', `Waiting for Deriv tick for ${normalized}…`);
      } catch (_) { scheduleReconnect(); }
    };
    connection.onmessage = event => {
      if (ws !== connection) return;
      try {
        const data = JSON.parse(event.data);
        if (data?.error) { setState('stale', data.error.message || 'Deriv rejected the tick subscription'); return; }
        if (data?.msg_type === 'tick' && data.tick?.quote != null) paintQuote(data.tick.quote, data.tick.epoch);
      } catch (_) {}
    };
    connection.onerror = () => {
      if (ws !== connection) return;
      setState('stale', 'Deriv market stream error; reconnecting…');
      try { connection.close(); } catch (_) {}
    };
    connection.onclose = () => {
      if (ws !== connection) return;
      ws = null;
      scheduleReconnect();
    };
  }

  function refreshConnection() {
    const symbol = String($('#symbol')?.value || '').trim();
    if (!symbol) { closeSocket(); activeSymbol = ''; setState('waiting', 'Select a broker instrument'); return; }
    if (symbol !== activeSymbol || !ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) connect(symbol);
  }

  function boot() {
    if (!$('.terminal-page')) return;
    ensurePanel();
    $('#symbol')?.addEventListener('change', refreshConnection);
    window.addEventListener('algobot:broker-symbols-loaded', refreshConnection);
    window.addEventListener('algobot:market-symbol-changed', event => connect(event.detail?.symbol || $('#symbol')?.value));
    window.addEventListener('algobot:account-changed', refreshConnection);
    window.addEventListener('algobot:account-synced', refreshConnection);
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) closeSocket();
      else refreshConnection();
    });
    healthTimer = setInterval(() => {
      if (document.hidden) return;
      const silenceSince = lastTickAt || socketStartedAt;
      if (ws && silenceSince && Date.now() - silenceSince > 15000 &&
          (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        setState('stale', 'No Deriv ticks received within 15 seconds; reconnecting…');
        closeSocket();
        scheduleReconnect();
        return;
      }
      refreshConnection();
    }, 5000);
    refreshConnection();
    window.addEventListener('pagehide', () => {
      stopped = true;
      if (healthTimer) clearInterval(healthTimer);
      closeSocket();
    }, {once: true});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
