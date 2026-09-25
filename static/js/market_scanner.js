(() => {
  'use strict';
  const form = document.querySelector('[data-market-scanner-form]');
  if (!form) return;

  const rows = document.querySelector('[data-scanner-rows]');
  const error = document.querySelector('[data-scanner-error]');
  const count = document.querySelector('[data-scanner-count]');
  const updated = document.querySelector('[data-scanner-updated]');
  const status = document.querySelector('[data-scanner-status]');
  const market = document.querySelector('[data-scanner-market]');
  const timeframe = document.querySelector('[data-scanner-timeframe]');
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
  const fmt = (value, digits = 4) =>
    value == null || value === '' || !Number.isFinite(Number(value))
      ? '—'
      : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });

  let timer = null;
  let requestId = 0;

  const setState = (kind, message) => {
    status.textContent = message;
    status.dataset.state = kind;
  };

  const render = data => {
    const results = Array.isArray(data.results) ? data.results : [];
    const existingMarket = market.value;
    const markets = [...new Set(results.map(row => row.market).filter(Boolean))].sort();

    if (market.options.length <= 1) {
      markets.forEach(value => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        market.appendChild(option);
      });
    }
    market.value = existingMarket;
    count.textContent = results.length + ' shown · ' + (data.total_available ?? 0) + ' available';
    updated.textContent = data.generated_at
      ? 'Updated ' + new Date(data.generated_at).toLocaleTimeString()
      : 'Updated ' + new Date().toLocaleTimeString();

    if (!results.length) {
      rows.innerHTML = '<tr><td colspan="12" class="scanner-empty">No markets match the current filters.</td></tr>';
      return;
    }

    rows.innerHTML = results.map(row => {
      const change = Number(row.change_percent);
      const state = row.status || 'no_data';
      const trend = row.trend || '—';
      const freshness = row.fresh
        ? (row.freshness_seconds == null ? 'LIVE' : row.freshness_seconds + 's old')
        : (state === 'stale' ? 'STALE' : 'NO DATA');
      const action = row.symbol
        ? '<a class="scanner-action" href="/trading/?symbol=' + encodeURIComponent(row.symbol) + '">Trade</a>'
        : '—';
      return '<tr>' +
        '<td><strong>' + esc(row.symbol) + '</strong><small>' + esc(row.display_name) + '</small></td>' +
        '<td>' + esc(row.market) + '</td>' +
        '<td>' + fmt(row.last_price) + '</td>' +
        '<td class="' + (change > 0 ? 'up' : change < 0 ? 'down' : '') + '">' +
          (Number.isFinite(change) ? (change > 0 ? '+' : '') + fmt(change, 2) + '%' : '—') + '</td>' +
        '<td>' + fmt(row.spread) + '</td>' +
        '<td>' + fmt(row.volume, 2) + '</td>' +
        '<td>' + fmt(row.rsi, 2) + '</td>' +
        '<td>' + esc(trend) + '</td>' +
        '<td>' + fmt(row.macd_histogram, 6) + '</td>' +
        '<td>' + esc(freshness) + '</td>' +
        '<td>' + esc(row.technical_status || '—') + '</td>' +
        '<td>' + action + '</td>' +
      '</tr>';
    }).join('');
  };

  const scan = async () => {
    const current = ++requestId;
    error.hidden = true;
    setState('loading', 'Scanning persisted broker data…');
    rows.innerHTML = '<tr><td colspan="12" class="scanner-empty">Scanning…</td></tr>';

    const params = new URLSearchParams({
      limit: '250',
      sort: 'change_percent',
      direction: document.querySelector('[data-scanner-direction]').value,
      timeframe: timeframe.value
    });
    [
      ['search', 'data-scanner-search'],
      ['market', 'data-scanner-market'],
      ['min_change', 'data-scanner-min-change'],
      ['max_change', 'data-scanner-max-change'],
      ['max_spread', 'data-scanner-max-spread'],
      ['min_rsi', 'data-scanner-min-rsi'],
      ['max_rsi', 'data-scanner-max-rsi'],
      ['trend', 'data-scanner-trend']
    ].forEach(([key, selector]) => {
      const element = document.querySelector('[' + selector + ']');
      const value = element?.value?.trim();
      if (value) params.set(key, value);
    });

    try {
      const request = window.AlgoBotFrontendData?.request;
      if (!request) throw new Error('AlgoBot market service is not ready.');
      const data = await request('/api/market/scanner/?' + params.toString(), {}, 15000);
      if (current !== requestId) return;
      if (data.status !== 'ok') throw new Error(data.detail || 'Scanner request failed.');
      render(data);
      setState('ready', 'Broker snapshot + persisted candles');
    } catch (scanError) {
      if (current !== requestId) return;
      error.textContent = scanError.message || 'Scanner unavailable.';
      error.hidden = false;
      rows.innerHTML = '<tr><td colspan="12" class="scanner-empty">Scanner unavailable. Retry when the broker feed is available.</td></tr>';
      setState('error', 'Scanner unavailable');
    }
  };

  form.addEventListener('submit', event => {
    event.preventDefault();
    scan();
  });
  document.querySelector('[data-scanner-refresh]')?.addEventListener('click', scan);
  document.querySelector('[data-scanner-reset]')?.addEventListener('click', () => {
    form.reset();
    scan();
  });

  const start = () => {
    clearInterval(timer);
    timer = setInterval(scan, 30000);
  };
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      scan();
      start();
    } else {
      clearInterval(timer);
    }
  });
  window.addEventListener('beforeunload', () => clearInterval(timer), { once: true });

  scan();
  start();
})();
