/* Real broker chart engine. All price/candle data comes from the connected broker API/WebSocket path. */
(() => {
  'use strict';
  if (window.__algoBotLiveChart) return;
  window.__algoBotLiveChart = true;

  const $ = selector => document.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const safe = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const money = value => Number.isFinite(Number(value)) ? Number(value).toLocaleString(undefined, {maximumFractionDigits: 8}) : 'Unavailable';
  const api = (url, options = {}, timeout = 10000) => window.AlgoBotFrontendData.request(url, options, timeout);
  const wsUrl = () => `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/market-data/`;
  const chartLib = () => window.LightweightCharts;

  let ws = null;
  let reconnect = null;
  let symbol = '';
  let mode = 'ticks';
  let timeframe = 60;
  let points = [];
  let candles = [];
  let caps = null;
  let chart = null;
  let mainSeries = null;
  let priceLine = null;
  let smaSeries = null;
  let emaSeries = null;
  let currentCandle = null;
  let closed = false;
  const indicators = {sma20: false, ema50: false};

  const accountReady = () => {
    const state = window.AlgoBotBrokerState?.get();
    return !!(window.AlgoBotBrokerAccounts?.length || state?.account);
  };

  const setStatus = text => $('[data-chart-loading]')?.replaceChildren(document.createTextNode(text));

  const updateInsights = values => {
    if (!values.length) return;
    const first = values[0];
    const last = values.at(-1);
    const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
    const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length;
    $('[data-trend]')?.replaceChildren(document.createTextNode(last >= first ? 'Bullish' : 'Bearish'));
    $('[data-volatility]')?.replaceChildren(document.createTextNode(money(Math.sqrt(variance))));
    $('[data-structure]')?.replaceChildren(document.createTextNode(mode === 'candles' ? 'Broker candles' : 'Broker ticks'));
    $('[data-chart-loading]')?.replaceChildren(document.createTextNode(`Live broker data · ${values.length} ${mode === 'candles' ? 'candles' : 'ticks'}`));
  };

  const normalizeEpoch = value => {
    const n = Number(value);
    if (!Number.isFinite(n)) return null;
    return n > 20000000000 ? Math.floor(n / 1000) : Math.floor(n);
  };

  const normalizePoints = items => list(items)
    .map(item => ({epoch: normalizeEpoch(item.epoch ?? item.time), price: Number(item.quote ?? item.price ?? item.close)}))
    .filter(item => Number.isFinite(item.epoch) && Number.isFinite(item.price))
    .sort((a, b) => a.epoch - b.epoch)
    .filter((item, index, array) => index === 0 || item.epoch >= array[index - 1].epoch)
    .slice(-500);

  const normalizeCandles = items => list(items)
    .map(item => ({
      time: normalizeEpoch(item.epoch ?? item.time),
      open: Number(item.open),
      high: Number(item.high),
      low: Number(item.low),
      close: Number(item.close),
    }))
    .filter(item => Number.isFinite(item.time) && [item.open, item.high, item.low, item.close].every(Number.isFinite))
    .sort((a, b) => a.time - b.time)
    .filter((item, index, array) => index === 0 || item.time > array[index - 1].time)
    .slice(-500);

  const values = () => mode === 'candles' ? candles.map(c => c.close) : points.map(p => p.price);

  const sma = (data, period) => data.map((_, index) => {
    if (index + 1 < period) return null;
    const window = data.slice(index + 1 - period, index + 1);
    return window.reduce((sum, value) => sum + value, 0) / period;
  }).map((value, index) => value == null ? null : ({time: mode === 'candles' ? candles[index].time : points[index].epoch, value})).filter(Boolean);

  const ema = (data, period) => {
    const result = [];
    const multiplier = 2 / (period + 1);
    let previous = null;
    data.forEach((value, index) => {
      if (index + 1 < period) return;
      if (previous == null) previous = data.slice(0, period).reduce((sum, item) => sum + item, 0) / period;
      else previous = (value - previous) * multiplier + previous;
      result.push({time: mode === 'candles' ? candles[index].time : points[index].epoch, value: previous});
    });
    return result;
  };

  const clearIndicators = () => {
    if (!chart) return;
    if (smaSeries) { chart.removeSeries(smaSeries); smaSeries = null; }
    if (emaSeries) { chart.removeSeries(emaSeries); emaSeries = null; }
  };

  const renderIndicators = () => {
    if (!chart || !mainSeries) return;
    clearIndicators();
    const data = values();
    if (indicators.sma20 && data.length >= 20) {
      smaSeries = chart.addSeries(chartLib().LineSeries, {color: '#f59e0b', lineWidth: 2, priceLineVisible: false, lastValueVisible: false});
      smaSeries.setData(sma(data, 20));
    }
    if (indicators.ema50 && data.length >= 50) {
      emaSeries = chart.addSeries(chartLib().LineSeries, {color: '#60a5fa', lineWidth: 2, priceLineVisible: false, lastValueVisible: false});
      emaSeries.setData(ema(data, 50));
    }
  };

  const createChart = () => {
    const container = $('#chart');
    const lib = chartLib();
    if (!container || !lib?.createChart) {
      setStatus('Interactive chart library unavailable');
      return false;
    }
    if (chart) chart.remove();
    container.innerHTML = '';
    chart = lib.createChart(container, {
      autoSize: true,
      layout: {background: {type: 'solid', color: 'transparent'}, textColor: '#a7b0bd'},
      grid: {vertLines: {color: 'rgba(148,163,184,.08)'}, horzLines: {color: 'rgba(148,163,184,.08)'}},
      crosshair: {mode: lib.CrosshairMode?.Normal ?? 0},
      rightPriceScale: {borderColor: 'rgba(148,163,184,.16)', scaleMargins: {top: .08, bottom: .08}},
      timeScale: {borderColor: 'rgba(148,163,184,.16)', timeVisible: true, secondsVisible: false, rightOffset: 5, barSpacing: 8},
      handleScroll: {mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true},
      handleScale: {axisPressedMouseMove: true, mouseWheel: true, pinch: true},
      localization: {priceFormatter: price => money(price)},
    });
    return true;
  };

  const createMainSeries = () => {
    if (!chart) return;
    clearIndicators();
    if (mainSeries) chart.removeSeries(mainSeries);
    const lib = chartLib();
    if (mode === 'candles') {
      mainSeries = chart.addSeries(lib.CandlestickSeries, {
        upColor: '#22c55e', downColor: '#ef4444', borderUpColor: '#22c55e', borderDownColor: '#ef4444',
        wickUpColor: '#22c55e', wickDownColor: '#ef4444',
      });
      mainSeries.setData(candles);
    } else {
      mainSeries = chart.addSeries(lib.LineSeries, {color: '#60a5fa', lineWidth: 2, priceLineVisible: false});
      mainSeries.setData(points.map(point => ({time: point.epoch, value: point.price})));
    }
    const last = mode === 'candles' ? candles.at(-1)?.close : points.at(-1)?.price;
    if (Number.isFinite(last)) {
      priceLine = mainSeries.createPriceLine({price: last, color: '#f8fafc', lineWidth: 1, lineStyle: lib.LineStyle?.Dotted ?? 1, axisLabelVisible: true, title: 'LIVE'});
    }
    renderIndicators();
    chart.timeScale().fitContent();
  };

  const refreshPriceLine = price => {
    if (!mainSeries || !Number.isFinite(price)) return;
    if (priceLine) mainSeries.removePriceLine(priceLine);
    const lib = chartLib();
    priceLine = mainSeries.createPriceLine({price, color: '#f8fafc', lineWidth: 1, lineStyle: lib.LineStyle?.Dotted ?? 1, axisLabelVisible: true, title: 'LIVE'});
  };

  const render = () => {
    if (!chart) createChart();
    if (!chart) return;
    createMainSeries();
    updateInsights(values());
  };

  const fit = () => chart?.timeScale().fitContent();
  const goLive = () => {
    if (!chart) return;
    chart.timeScale().scrollToRealTime();
  };

  const renderCaps = data => {
    caps = data || {};
    const tf = Array.isArray(caps.timeframes) ? caps.timeframes : [];
    if (!tf.length) {
      setStatus('Broker did not publish chart timeframes');
      return;
    }
    const select = $('#timeframe');
    const box = $('[data-chart-timeframes]');
    timeframe = Number(select?.value || tf[0].seconds);
    if (select) select.innerHTML = tf.map(item => `<option value="${safe(item.seconds)}">${safe(item.label)}</option>`).join('');
    if (select) { select.value = String(timeframe); if (!select.value) { timeframe = Number(tf[0].seconds); select.value = String(timeframe); } }
    if (box) {
      box.innerHTML = tf.map(item => `<button type="button" data-broker-timeframe="${safe(item.seconds)}" class="${Number(item.seconds) === timeframe ? 'active' : ''}">${safe(item.label)}</button>`).join('');
      box.querySelectorAll('button').forEach(button => button.addEventListener('click', () => {
        box.querySelectorAll('button').forEach(item => item.classList.remove('active'));
        button.classList.add('active');
        timeframe = Number(button.dataset.brokerTimeframe);
        if (select) select.value = String(timeframe);
        if (mode === 'candles') loadHistory();
      }));
    }
  };

  async function loadCaps() {
    if (!accountReady()) return;
    try { renderCaps(await api('/api/market/chart/capabilities/', {}, 9000)); }
    catch (error) { setStatus(`Broker chart capabilities unavailable: ${error.message || 'request failed'}`); }
  }

  async function loadHistory() {
    if (!symbol || !accountReady()) return;
    setStatus(`Loading ${safe(symbol)} broker ${mode === 'candles' ? 'candles' : 'ticks'}…`);
    try {
      const params = new URLSearchParams({symbol, mode, limit: '500'});
      if (mode === 'candles') params.set('granularity', String(timeframe));
      const data = await api(`/api/market/chart/history/?${params.toString()}`, {}, 12000);
      if (String(data.symbol || symbol) !== symbol) throw new Error('Broker returned a different symbol');
      if (mode === 'candles') {
        candles = normalizeCandles(data.items);
        points = [];
        currentCandle = candles.at(-1) || null;
      } else {
        points = normalizePoints(data.items);
        candles = [];
        currentCandle = null;
      }
      render();
      goLive();
    } catch (error) {
      setStatus(`Live broker chart history unavailable: ${error.message || 'request failed'}`);
    }
  }

  const updateCandleFromTick = tick => {
    const epoch = normalizeEpoch(tick.epoch) || Math.floor(Date.now() / 1000);
    const price = Number(tick.price);
    const bucket = Math.floor(epoch / timeframe) * timeframe;
    if (!Number.isFinite(price)) return;
    if (!currentCandle || currentCandle.time !== bucket) {
      currentCandle = {time: bucket, open: price, high: price, low: price, close: price};
      candles.push(currentCandle);
      candles = candles.slice(-500);
    } else {
      currentCandle.high = Math.max(currentCandle.high, price);
      currentCandle.low = Math.min(currentCandle.low, price);
      currentCandle.close = price;
    }
    if (mainSeries) mainSeries.update(currentCandle);
    refreshPriceLine(price);
    renderIndicators();
    updateInsights(candles.map(c => c.close));
  };

  const updateLineFromTick = tick => {
    const epoch = normalizeEpoch(tick.epoch) || Math.floor(Date.now() / 1000);
    const price = Number(tick.price);
    if (!Number.isFinite(price)) return;
    const existing = points.find(point => point.epoch === epoch);
    if (existing) existing.price = price;
    else points.push({epoch, price});
    points = points.sort((a, b) => a.epoch - b.epoch).slice(-500);
    if (mainSeries) mainSeries.update({time: epoch, value: price});
    refreshPriceLine(price);
    renderIndicators();
    updateInsights(points.map(p => p.price));
  };

  function closeSocket() {
    if (ws) { try { ws.close(); } catch (_) {} ws = null; }
    clearTimeout(reconnect);
  }

  function connect(nextSymbol) {
    if (!nextSymbol || document.visibilityState !== 'visible' || !accountReady()) return;
    symbol = nextSymbol;
    closed = false;
    closeSocket();
    try {
      ws = new WebSocket(wsUrl());
      ws.addEventListener('open', () => ws?.send(JSON.stringify({action: 'subscribe', symbol})));
      ws.addEventListener('message', event => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type !== 'market.tick' || String(payload.symbol || symbol) !== symbol) return;
          const price = Number(payload.price);
          if (!Number.isFinite(price)) return;
          $('[data-q="bid"]')?.replaceChildren(document.createTextNode(money(payload.bid ?? price)));
          $('[data-q="ask"]')?.replaceChildren(document.createTextNode(money(payload.ask ?? price)));
          if (mode === 'candles') updateCandleFromTick(payload);
          else updateLineFromTick(payload);
        } catch (_) {}
      });
      ws.addEventListener('close', () => {
        ws = null;
        if (!closed && document.visibilityState === 'visible' && accountReady()) {
          setStatus('Broker market stream reconnecting…');
          reconnect = setTimeout(() => connect(symbol), 2500);
        }
      });
      ws.addEventListener('error', () => setStatus('Broker market stream reconnecting…'));
    } catch (_) {
      reconnect = setTimeout(() => connect(symbol), 2500);
    }
  }

  function setMode(nextMode) {
    mode = nextMode;
    document.querySelectorAll('[data-chart-mode]').forEach(button => button.classList.toggle('active', button.dataset.chartMode === mode));
    const box = $('[data-chart-timeframes]');
    if (box) box.style.display = mode === 'candles' ? '' : 'none';
    loadHistory();
  }

  function bind() {
    const select = $('#symbol');
    if (!select || select.dataset.chartBound === '1') return;
    select.dataset.chartBound = '1';
    document.querySelectorAll('[data-chart-mode]').forEach(button => button.addEventListener('click', () => setMode(button.dataset.chartMode)));
    document.querySelectorAll('[data-chart-action]').forEach(button => button.addEventListener('click', () => button.dataset.chartAction === 'fit' ? fit() : goLive()));
    document.querySelectorAll('[data-indicator]').forEach(button => button.addEventListener('click', () => {
      const name = button.dataset.indicator;
      indicators[name] = !indicators[name];
      button.classList.toggle('active', indicators[name]);
      renderIndicators();
    }));
    select.addEventListener('change', () => {
      symbol = select.value;
      points = [];
      candles = [];
      currentCandle = null;
      closeSocket();
      if (symbol) { loadHistory(); connect(symbol); }
    });
    $('#timeframe')?.addEventListener('change', () => {
      timeframe = Number($('#timeframe').value || 60);
      if (mode === 'candles') loadHistory();
    });
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && select.value && accountReady()) { loadHistory(); connect(select.value); }
      else if (document.visibilityState !== 'visible') { closed = true; closeSocket(); }
    });
    window.addEventListener('resize', () => chart?.applyOptions({autoSize: true}));
  }

  async function start() {
    if (document.body.dataset.authenticated !== 'true' || !$('#chart')) return;
    bind();
    if (!createChart()) return;
    let attempts = 0;
    const waitForSymbol = async () => {
      const select = $('#symbol');
      if (select?.value) {
        symbol = select.value;
        await loadCaps();
        await loadHistory();
        connect(symbol);
        return;
      }
      if (++attempts < 40) setTimeout(waitForSymbol, 250);
      else setStatus('No broker market instrument available');
    };
    waitForSymbol();
    window.AlgoBotBrokerState?.subscribe(() => {
      const select = $('#symbol');
      if (select?.value) { loadCaps(); loadHistory(); connect(select.value); }
    });
    window.addEventListener('algobot:backend-accounts-loaded', () => {
      const select = $('#symbol');
      if (select?.value) { loadCaps(); loadHistory(); connect(select.value); }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once: true});
  else start();
})();
