/* Deriv-native broker chart engine. Historical and live market data come directly from Deriv's public market-data WebSocket. */
(() => {
  'use strict';
  if (window.__algoBotLiveChart) return;
  window.__algoBotLiveChart = true;

  const $ = selector => document.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const safe = value => String(value ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[c]));
  const money = value => Number.isFinite(Number(value)) ? Number(value).toLocaleString(undefined, {maximumFractionDigits: 8}) : 'Unavailable';
  const api = (url, options = {}, timeout = 10000) => window.AlgoBotFrontendData.request(url, options, timeout);
  const DERIV_PUBLIC_WS = 'wss://api.derivws.com/trading/v1/options/ws/public';
  const chartLib = () => window.LightweightCharts;
  const DERIV_TIMEFRAMES = [
    {label:'1m', seconds:60}, {label:'2m', seconds:120}, {label:'5m', seconds:300},
    {label:'10m', seconds:600}, {label:'15m', seconds:900}, {label:'30m', seconds:1800},
    {label:'1h', seconds:3600}, {label:'2h', seconds:7200}, {label:'4h', seconds:14400},
    {label:'8h', seconds:28800}, {label:'1d', seconds:86400},
  ];

  let ws = null;
  let reconnect = null;
  let requestId = 1000;
  let symbol = '';
  let mode = 'ticks';
  let timeframe = 60;
  let points = [];
  let candles = [];
  let chart = null;
  let mainSeries = null;
  let priceLine = null;
  let smaSeries = null;
  let emaSeries = null;
  let currentCandle = null;
  let closed = false;
  const indicators = {sma20:false, ema50:false};

  const accountReady = () => {
    const state = window.AlgoBotBrokerState?.get();
    return !!(window.AlgoBotBrokerAccounts?.length || state?.account);
  };
  const setStatus = text => $('[data-chart-loading]')?.replaceChildren(document.createTextNode(text));
  const normalizeEpoch = value => {
    const n = Number(value);
    if (!Number.isFinite(n)) return null;
    return n > 20000000000 ? Math.floor(n / 1000) : Math.floor(n);
  };

  const normalizePoints = items => list(items)
    .map(item => ({epoch:normalizeEpoch(item.epoch ?? item.time), price:Number(item.quote ?? item.price ?? item.close)}))
    .filter(item => Number.isFinite(item.epoch) && Number.isFinite(item.price))
    .sort((a,b) => a.epoch-b.epoch)
    .filter((item,index,array) => index === 0 || item.epoch > array[index-1].epoch)
    .slice(-500);

  const normalizeCandles = items => list(items)
    .map(item => ({time:normalizeEpoch(item.epoch ?? item.time), open:Number(item.open), high:Number(item.high), low:Number(item.low), close:Number(item.close)}))
    .filter(item => Number.isFinite(item.time) && [item.open,item.high,item.low,item.close].every(Number.isFinite))
    .sort((a,b) => a.time-b.time)
    .filter((item,index,array) => index === 0 || item.time > array[index-1].time)
    .slice(-500);

  const values = () => mode === 'candles' ? candles.map(c => c.close) : points.map(p => p.price);
  const sma = (data, period) => data.map((_,i) => i + 1 < period ? null : data.slice(i + 1 - period, i + 1).reduce((s,v) => s + v, 0) / period)
    .map((value,i) => value == null ? null : ({time:mode === 'candles' ? candles[i].time : points[i].epoch, value})).filter(Boolean);
  const ema = (data, period) => {
    const result = [], multiplier = 2 / (period + 1); let previous = null;
    data.forEach((value,i) => {
      if (i + 1 < period) return;
      if (previous == null) previous = data.slice(0,period).reduce((s,v) => s + v, 0) / period;
      else previous = (value - previous) * multiplier + previous;
      result.push({time:mode === 'candles' ? candles[i].time : points[i].epoch, value:previous});
    });
    return result;
  };

  const updateInsights = data => {
    if (!data.length) return;
    const first = data[0], last = data.at(-1);
    const mean = data.reduce((s,v) => s + v, 0) / data.length;
    const variance = data.reduce((s,v) => s + (v - mean) ** 2, 0) / data.length;
    $('[data-trend]')?.replaceChildren(document.createTextNode(last >= first ? 'Bullish' : 'Bearish'));
    $('[data-volatility]')?.replaceChildren(document.createTextNode(money(Math.sqrt(variance))));
    $('[data-structure]')?.replaceChildren(document.createTextNode(mode === 'candles' ? 'Deriv broker candles' : 'Deriv broker ticks'));
    setStatus(`Live Deriv data · ${data.length} ${mode === 'candles' ? 'candles' : 'ticks'}`);
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
      smaSeries = chart.addSeries(chartLib().LineSeries, {color:'#f59e0b', lineWidth:2, priceLineVisible:false, lastValueVisible:false});
      smaSeries.setData(sma(data,20));
    }
    if (indicators.ema50 && data.length >= 50) {
      emaSeries = chart.addSeries(chartLib().LineSeries, {color:'#60a5fa', lineWidth:2, priceLineVisible:false, lastValueVisible:false});
      emaSeries.setData(ema(data,50));
    }
  };

  const createChart = () => {
    const container = $('#chart'), lib = chartLib();
    if (!container || !lib?.createChart) { setStatus('Interactive chart library unavailable'); return false; }
    if (chart) chart.remove();
    container.innerHTML = '';
    chart = lib.createChart(container, {
      autoSize:true,
      layout:{background:{type:'solid',color:'transparent'},textColor:'#a7b0bd'},
      grid:{vertLines:{color:'rgba(148,163,184,.08)'},horzLines:{color:'rgba(148,163,184,.08)'}},
      crosshair:{mode:lib.CrosshairMode?.Normal ?? 0},
      rightPriceScale:{borderColor:'rgba(148,163,184,.16)',scaleMargins:{top:.08,bottom:.08}},
      timeScale:{borderColor:'rgba(148,163,184,.16)',timeVisible:true,secondsVisible:false,rightOffset:5,barSpacing:8},
      handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:true},
      handleScale:{axisPressedMouseMove:true,mouseWheel:true,pinch:true},
      localization:{priceFormatter:price => money(price)},
    });
    return true;
  };

  const createMainSeries = () => {
    if (!chart) return;
    clearIndicators();
    if (mainSeries) chart.removeSeries(mainSeries);
    const lib = chartLib();
    if (mode === 'candles') {
      mainSeries = chart.addSeries(lib.CandlestickSeries,{upColor:'#22c55e',downColor:'#ef4444',borderUpColor:'#22c55e',borderDownColor:'#ef4444',wickUpColor:'#22c55e',wickDownColor:'#ef4444'});
      mainSeries.setData(candles);
    } else {
      mainSeries = chart.addSeries(lib.LineSeries,{color:'#60a5fa',lineWidth:2,priceLineVisible:false});
      mainSeries.setData(points.map(p => ({time:p.epoch,value:p.price})));
    }
    const last = mode === 'candles' ? candles.at(-1)?.close : points.at(-1)?.price;
    if (Number.isFinite(last)) {
      priceLine = mainSeries.createPriceLine({price:last,color:'#f8fafc',lineWidth:1,lineStyle:lib.LineStyle?.Dotted ?? 1,axisLabelVisible:true,title:'LIVE'});
    }
    renderIndicators();
    chart.timeScale().fitContent();
  };

  const refreshPriceLine = price => {
    if (!mainSeries || !Number.isFinite(price)) return;
    if (priceLine) mainSeries.removePriceLine(priceLine);
    const lib = chartLib();
    priceLine = mainSeries.createPriceLine({price,color:'#f8fafc',lineWidth:1,lineStyle:lib.LineStyle?.Dotted ?? 1,axisLabelVisible:true,title:'LIVE'});
  };
  const render = () => { if (!chart) createChart(); if (chart) { createMainSeries(); updateInsights(values()); } };
  const fit = () => chart?.timeScale().fitContent();
  const goLive = () => chart?.timeScale().scrollToRealTime();

  const renderCaps = () => {
    const tf = DERIV_TIMEFRAMES, select = $('#timeframe'), box = $('[data-chart-timeframes]');
    timeframe = Number(select?.value || tf[0].seconds);
    if (select) select.innerHTML = tf.map(item => `<option value="${item.seconds}">${safe(item.label)}</option>`).join('');
    if (select) { select.value = String(timeframe); if (!select.value) { timeframe = 60; select.value = '60'; } }
    if (box) {
      box.innerHTML = tf.map(item => `<button type="button" data-broker-timeframe="${item.seconds}" class="${item.seconds === timeframe ? 'active' : ''}">${safe(item.label)}</button>`).join('');
      box.querySelectorAll('button').forEach(button => button.addEventListener('click', () => {
        box.querySelectorAll('button').forEach(item => item.classList.remove('active'));
        button.classList.add('active'); timeframe = Number(button.dataset.brokerTimeframe);
        if (select) select.value = String(timeframe);
        if (mode === 'candles') loadHistory();
      }));
    }
  };

  const derivRequest = (payload, timeoutMs = 12000) => new Promise((resolve,reject) => {
    let socket, timer;
    const reqId = ++requestId;
    const finish = (error,data) => { clearTimeout(timer); try { socket?.close(); } catch (_) {} error ? reject(error) : resolve(data); };
    try { socket = new WebSocket(DERIV_PUBLIC_WS); }
    catch (error) { reject(error); return; }
    timer = setTimeout(() => finish(new Error('Deriv market-data request timed out')), timeoutMs);
    socket.addEventListener('open', () => socket.send(JSON.stringify({...payload, req_id:reqId})));
    socket.addEventListener('message', event => {
      try {
        const data = JSON.parse(event.data);
        if (data.error) { finish(new Error(data.error.message || 'Deriv rejected the market-data request')); return; }
        if (Number(data.req_id) === reqId || data.msg_type === 'history' || data.msg_type === 'candles') finish(null,data);
      } catch (error) { finish(error); }
    });
    socket.addEventListener('error', () => finish(new Error('Deriv public market-data connection failed')));
    socket.addEventListener('close', event => { if (event.code && event.code !== 1000) finish(new Error('Deriv public market-data connection closed')); });
  });

  async function loadCaps() { renderCaps(); }

  async function loadHistory() {
    if (!symbol || !accountReady()) return;
    setStatus(`Loading ${safe(symbol)} directly from Deriv…`);
    try {
      let data;
      if (mode === 'candles') {
        data = await derivRequest({ticks_history:symbol,end:'latest',count:500,style:'candles',granularity:timeframe});
        candles = normalizeCandles(data.candles || []); points = []; currentCandle = candles.at(-1) || null;
      } else {
        data = await derivRequest({ticks_history:symbol,end:'latest',count:500,style:'ticks'});
        const history = data.history || {};
        points = normalizePoints((history.times || []).map((epoch,i) => ({epoch,quote:(history.prices || [])[i]})));
        candles = []; currentCandle = null;
      }
      render(); goLive();
    } catch (directError) {
      // Backend remains an authoritative fallback for rolling deployments,
      // but normal chart traffic no longer depends on the Render instance.
      try {
        const params = new URLSearchParams({symbol,mode,limit:'500'});
        if (mode === 'candles') params.set('granularity',String(timeframe));
        const data = await api(`/api/market/chart/history/?${params.toString()}`,{},12000);
        if (String(data.symbol || symbol) !== symbol) throw new Error('Broker returned a different symbol');
        if (mode === 'candles') { candles = normalizeCandles(data.items); points = []; currentCandle = candles.at(-1) || null; }
        else { points = normalizePoints(data.items); candles = []; currentCandle = null; }
        render(); goLive();
      } catch (fallbackError) {
        setStatus(`Live broker chart history unavailable: ${fallbackError.message || directError.message}`);
      }
    }
  }

  const updateCandleFromTick = tick => {
    const epoch = normalizeEpoch(tick.epoch) || Math.floor(Date.now()/1000), price = Number(tick.price), bucket = Math.floor(epoch/timeframe)*timeframe;
    if (!Number.isFinite(price)) return;
    if (!currentCandle || currentCandle.time !== bucket) {
      currentCandle = {time:bucket,open:price,high:price,low:price,close:price};
      candles.push(currentCandle); candles = candles.slice(-500);
    } else {
      currentCandle.high = Math.max(currentCandle.high,price); currentCandle.low = Math.min(currentCandle.low,price); currentCandle.close = price;
    }
    mainSeries?.update(currentCandle); refreshPriceLine(price); renderIndicators(); updateInsights(candles.map(c => c.close));
  };

  const updateLineFromTick = tick => {
    const epoch = normalizeEpoch(tick.epoch) || Math.floor(Date.now()/1000), price = Number(tick.price);
    if (!Number.isFinite(price)) return;
    const existing = points.find(p => p.epoch === epoch);
    if (existing) existing.price = price; else points.push({epoch,price});
    points.sort((a,b) => a.epoch-b.epoch); points = points.slice(-500);
    mainSeries?.update({time:epoch,value:price}); refreshPriceLine(price); renderIndicators(); updateInsights(points.map(p => p.price));
  };

  function closeSocket() {
    if (ws) { try { ws.close(); } catch (_) {} ws = null; }
    clearTimeout(reconnect);
  }

  function connect(nextSymbol) {
    if (!nextSymbol || document.visibilityState !== 'visible' || !accountReady()) return;
    symbol = nextSymbol; closed = false; closeSocket();
    try {
      ws = new WebSocket(DERIV_PUBLIC_WS);
      ws.addEventListener('open', () => {
        ws?.send(JSON.stringify({ticks:symbol,subscribe:1,req_id:++requestId}));
        setStatus(`Connected directly to Deriv · ${symbol}`);
      });
      ws.addEventListener('message', event => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.error) { setStatus(`Deriv stream error: ${payload.error.message || 'request rejected'}`); return; }
          if (payload.msg_type !== 'tick') return;
          const tick = payload.tick || {};
          if (String(tick.symbol || payload.echo_req?.ticks || symbol) !== symbol) return;
          const price = Number(tick.quote); if (!Number.isFinite(price)) return;
          const liveTick = {price,epoch:tick.epoch,bid:tick.bid,ask:tick.ask};
          $('[data-q="bid"]')?.replaceChildren(document.createTextNode(money(tick.bid ?? price)));
          $('[data-q="ask"]')?.replaceChildren(document.createTextNode(money(tick.ask ?? price)));
          if (mode === 'candles') updateCandleFromTick(liveTick); else updateLineFromTick(liveTick);
        } catch (_) {}
      });
      ws.addEventListener('close', () => {
        ws = null;
        if (!closed && document.visibilityState === 'visible' && accountReady()) {
          setStatus('Deriv market stream reconnecting…'); reconnect = setTimeout(() => connect(symbol),2500);
        }
      });
      ws.addEventListener('error', () => setStatus('Deriv market stream reconnecting…'));
    } catch (_) { reconnect = setTimeout(() => connect(symbol),2500); }
  }

  function setMode(nextMode) {
    mode = nextMode;
    document.querySelectorAll('[data-chart-mode]').forEach(button => button.classList.toggle('active',button.dataset.chartMode === mode));
    const box = $('[data-chart-timeframes]'); if (box) box.style.display = mode === 'candles' ? '' : 'none';
    loadHistory();
  }

  function bind() {
    const select = $('#symbol'); if (!select || select.dataset.chartBound === '1') return;
    select.dataset.chartBound = '1';
    document.querySelectorAll('[data-chart-mode]').forEach(button => button.addEventListener('click',() => setMode(button.dataset.chartMode)));
    document.querySelectorAll('[data-chart-action]').forEach(button => button.addEventListener('click',() => button.dataset.chartAction === 'fit' ? fit() : goLive()));
    document.querySelectorAll('[data-indicator]').forEach(button => button.addEventListener('click',() => { const name = button.dataset.indicator; indicators[name] = !indicators[name]; button.classList.toggle('active',indicators[name]); renderIndicators(); }));
    select.addEventListener('change',() => { symbol = select.value; points=[]; candles=[]; currentCandle=null; closeSocket(); if (symbol) { loadHistory(); connect(symbol); } });
    $('#timeframe')?.addEventListener('change',() => { timeframe = Number($('#timeframe').value || 60); if (mode === 'candles') loadHistory(); });
    document.addEventListener('visibilitychange',() => { if (document.visibilityState === 'visible' && select.value && accountReady()) { loadHistory(); connect(select.value); } else if (document.visibilityState !== 'visible') { closed=true; closeSocket(); } });
    window.addEventListener('resize',() => chart?.applyOptions({autoSize:true}));
  }

  async function start() {
    if (document.body.dataset.authenticated !== 'true' || !$('#chart')) return;
    bind(); if (!createChart()) return;
    renderCaps();
    let attempts = 0;
    const waitForSymbol = async () => {
      const select = $('#symbol');
      if (select?.value) { symbol = select.value; await loadHistory(); connect(symbol); return; }
      if (++attempts < 40) setTimeout(waitForSymbol,250); else setStatus('No broker market instrument available');
    };
    waitForSymbol();
    window.addEventListener('algobot:backend-accounts-loaded',() => { const select = $('#symbol'); if (select?.value) { loadHistory(); connect(select.value); } });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',start,{once:true}); else start();
})();