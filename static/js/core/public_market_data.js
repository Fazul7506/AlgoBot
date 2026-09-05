/* Public Deriv market metadata fallback.
 * Catalogue and quote discovery are broker-public data and do not require a
 * selected trading account. Authenticated execution remains API-only.
 */
(() => {
  'use strict';
  if (window.AlgoBotPublicMarketData) return;

  const WS_URL = 'wss://api.derivws.com/trading/v1/options/ws/public';
  let requestId = 50000;

  function request(payload, timeout = 7000) {
    return new Promise((resolve, reject) => {
      let settled = false;
      let socket = null;
      const timer = setTimeout(() => {
        if (settled) return;
        settled = true;
        try { socket?.close(); } catch (_) {}
        reject(new Error('Public broker market-data request timed out'));
      }, Math.max(1000, timeout));

      const finish = (error, value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        try { socket?.close(); } catch (_) {}
        error ? reject(error) : resolve(value);
      };

      try {
        socket = new WebSocket(WS_URL);
        socket.addEventListener('open', () => {
          socket?.send(JSON.stringify({ ...payload, req_id: ++requestId }));
        }, { once: true });
        socket.addEventListener('message', event => {
          try {
            const response = JSON.parse(event.data);
            if (response?.error) {
              finish(new Error(response.error.message || 'Broker market-data request failed'));
              return;
            }
            finish(null, response);
          } catch (_) {
            finish(new Error('Broker returned invalid market-data JSON'));
          }
        });
        socket.addEventListener('error', () => finish(new Error('Public broker market-data connection failed')), { once: true });
        socket.addEventListener('close', () => {
          if (!settled) finish(new Error('Public broker market-data connection closed'));
        }, { once: true });
      } catch (error) {
        finish(error instanceof Error ? error : new Error('Public broker market-data connection failed'));
      }
    });
  }

  async function catalogue(timeout = 7000) {
    const response = await request({ active_symbols: 'brief' }, timeout);
    const rows = Array.isArray(response?.active_symbols) ? response.active_symbols : [];
    return rows.filter(row => row?.underlying_symbol).map(row => {
      const suspended = Boolean(row.is_trading_suspended);
      const exchangeOpen = row.exchange_is_open !== false;
      return {
        symbol: String(row.underlying_symbol),
        display_name: String(row.underlying_symbol_name || row.underlying_symbol),
        market: String(row.market || ''),
        sub_market: String(row.submarket || row.subgroup || ''),
        symbol_type: String(row.underlying_symbol_type || ''),
        pip_size: row.pip_size ?? 2,
        is_active: !suspended,
        is_tradable: exchangeOpen && !suspended,
        exchange_is_open: exchangeOpen,
        is_trading_suspended: suspended,
      };
    }).filter(row => row.is_active);
  }

  async function tick(symbol, timeout = 7000) {
    const value = String(symbol || '').trim();
    if (!value) throw new Error('A broker symbol is required');
    const response = await request({ ticks: value }, timeout);
    const raw = response?.tick || {};
    const quote = Number(raw.quote);
    if (!Number.isFinite(quote)) throw new Error(`Broker returned no quote for ${value}`);
    return {
      symbol: value,
      quote,
      bid: raw.bid == null ? quote : Number(raw.bid),
      ask: raw.ask == null ? quote : Number(raw.ask),
      epoch: Number(raw.epoch || 0),
      volume: Number(raw.volume || 0),
    };
  }

  window.AlgoBotPublicMarketData = Object.freeze({ catalogue, tick, websocketUrl: WS_URL });
})();
