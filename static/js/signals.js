(() => {
  'use strict';
  if (window.__algoBotSignalsPage) return;
  window.__algoBotSignalsPage = true;

  const $ = id => document.getElementById(id);
  const F = (v, d = 5) => v == null || !Number.isFinite(Number(v)) ? '—' : Number(v).toLocaleString(undefined, {maximumFractionDigits: d});
  const esc = s => String(s ?? '—').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  const tone = s => String(s || '').toLowerCase().includes('bull') || String(s || '').toLowerCase() === 'buy' ? 'bull' : String(s || '').toLowerCase().includes('bear') || String(s || '').toLowerCase() === 'sell' ? 'bear' : 'neutral';
  const arr = (v) => Array.isArray(v) ? v : [];
  const val = (obj, ...keys) => {
    for (const key of keys) {
      const parts = String(key).split('.');
      let value = obj;
      for (const part of parts) value = value == null ? undefined : value[part];
      if (value !== undefined && value !== null && value !== '') return value;
    }
    return '—';
  };
  const list = (id, items, formatter) => {
    const el = $(id);
    if (!el) return;
    el.innerHTML = arr(items).length ? arr(items).map(formatter).join('') : '<span class="muted">No events detected.</span>';
  };
  const status = (ok, text) => { $('sDot').className = 'dot' + (ok ? ' live' : ''); $('sStatus').textContent = text; };

  const S = { markets: [], selected: null, scan: [], timer: null };

  async function getJson(url) {
    const response = await fetch(url, {headers: {Accept: 'application/json'}, credentials: 'same-origin', cache: 'no-store'});
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || data.error || 'Request failed');
    return data;
  }

  function renderChart(d) {
    const canvas = $('sChart'), empty = $('sEmpty');
    if (!canvas) return;
    const box = canvas.getBoundingClientRect(), q = window.devicePixelRatio || 1;
    const w = Math.max(320, box.width), h = Math.max(250, box.height);
    canvas.width = w * q; canvas.height = h * q;
    const ctx = canvas.getContext('2d'); ctx.setTransform(q, 0, 0, q, 0, 0); ctx.clearRect(0, 0, w, h);
    const candles = arr(d.last_candles);
    if (!candles.length) { canvas.hidden = true; empty.hidden = false; return; }
    canvas.hidden = false; empty.hidden = true;
    const hi = Math.max(...candles.map(v => Number(v.high))), lo = Math.min(...candles.map(v => Number(v.low))), span = hi - lo || 1;
    const py = z => h - 18 - (Number(z) - lo) / span * (h - 36);
    for (let i = 1; i < 6; i++) { ctx.strokeStyle = 'rgba(148,163,184,.12)'; ctx.beginPath(); ctx.moveTo(0, h*i/6); ctx.lineTo(w, h*i/6); ctx.stroke(); }
    const cw = Math.max(2, Math.min(11, w / candles.length * .65));
    candles.forEach((v, i) => {
      const x = i * w / (candles.length - 1 || 1), up = Number(v.close) >= Number(v.open);
      ctx.strokeStyle = up ? '#4ade80' : '#fb7185'; ctx.fillStyle = ctx.strokeStyle;
      ctx.beginPath(); ctx.moveTo(x, py(v.high)); ctx.lineTo(x, py(v.low)); ctx.stroke();
      const top = Math.min(py(v.open), py(v.close)), bh = Math.max(1, Math.abs(py(v.close) - py(v.open)));
      ctx.fillRect(x - cw/2, top, cw, bh);
    });
    [['sSup', d.levels?.support], ['sRes', d.levels?.resistance]].forEach(([id, v]) => {
      if (v == null) return;
      const y = py(v); ctx.strokeStyle = 'rgba(251,191,36,.55)'; ctx.setLineDash([5,5]); ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke(); ctx.setLineDash([]);
    });
  }

  function render(d) {
    S.selected = d;
    $('sName').textContent = d.display_name || d.symbol || '—';
    $('sPrice').textContent = F(d.price);
    $('sSignal').textContent = d.signal || '—'; $('sSignal').className = tone(d.signal);
    $('sScore').textContent = d.score != null ? `${F(d.score,1)}/100` : '—';
    $('sConfidence').textContent = d.confidence != null ? `${F(d.confidence,1)}%` : '—';
    $('sRegime').textContent = d.volatility_regime || d.regime || '—';
    $('sStructure').textContent = d.structure || '—';
    $('sRes').textContent = F(d.levels?.resistance); $('sSup').textContent = F(d.levels?.support);
    $('sRange').textContent = F(d.levels?.range); $('sChange').textContent = d.change_pct != null ? `${F(d.change_pct,2)}%` : '—';
    const i = d.indicators || {};
    $('sS20').textContent = F(i.sma20); $('sS50').textContent = F(i.sma50); $('sS200').textContent = F(i.sma200); $('sEma').textContent = `${F(i.ema9)} / ${F(i.ema21)}`;
    $('sRsi').textContent = F(i.rsi14,2); $('sAtr').textContent = F(i.atr14); $('sMacd').textContent = F(i.macd?.histogram); $('sBb').textContent = i.bollinger?.width != null ? `${F(i.bollinger.width,2)}%` : '—';
    const factors = arr(d.factors); $('sFactors').textContent = `${factors.length} factors`;
    $('sToolStructure').textContent = d.structure || '—'; $('sToolSweep').textContent = d.liquidity_sweeps || d.liquidity_sweep || '—';
    $('sToolFvg').textContent = d.fvg_count != null ? `${d.fvg_count} detected` : val(d, 'fvg_status', 'fair_value_gaps');
    $('sToolZones').textContent = d.supply_demand || d.zone_status || '—'; $('sToolPatterns').textContent = d.pattern_summary || '—';
    $('sToolRegime').textContent = d.volatility_regime || '—'; $('sToolConfluence').textContent = d.signal ? `${d.signal} · ${F(d.confidence,1)}% confidence` : '—';
    $('sEvidence').innerHTML = factors.map(v => `<span class="chip">${esc(v)}</span>`).join('') || '<span class="muted">No additional factors.</span>';
    list('sStructureList', d.structure_events || d.structure_points, v => `<div class="list-row"><span>${esc(v)}</span></div>`);
    list('sSweepList', d.liquidity_events || d.liquidity_sweeps_list, v => `<div class="list-row"><span>${esc(v)}</span></div>`);
    list('sFvgList', d.fvgs || d.fair_value_gaps, v => `<div class="list-row"><span>${esc(v.name || v.type || v)}</span><span>${esc(v.price || v.range || '')}</span></div>`);
    list('sZoneList', d.zones || d.supply_demand_zones, v => `<div class="list-row"><span>${esc(v.type || v.zone || v)}</span><span>${esc(v.price || v.range || '')}</span></div>`);
    list('sPatternList', d.patterns || d.candlestick_patterns, v => `<div class="list-row"><span>${esc(v.name || v.pattern || v)}</span></div>`);
    list('sFibList', d.fibonacci_levels || d.fibonacci, v => `<div class="list-row"><span>${esc(v.level || v.name || v)}</span><span>${esc(v.price || '')}</span></div>`);
    renderChart(d);
  }

  function renderScan() {
    const tbody = $('sScanner');
    if (!tbody) return;
    $('sScanCount').textContent = `${S.scan.length} markets`;
    tbody.innerHTML = S.scan.map(d => {
      const market = S.markets.find(m => m.symbol === d.symbol) || {};
      return `<tr data-symbol="${esc(d.symbol)}"><td><strong>${esc(d.display_name || market.display_name || d.symbol)}</strong><br><small>${esc(d.symbol)}</small></td><td>${esc(d.market || market.market || market.sub_market || '—')}</td><td>${esc(d.timeframe || $('sTf').value)}</td><td>${esc(F(d.price))}</td><td class="${tone(d.signal)}">${esc(d.signal || '—')}</td><td>${esc(d.score == null ? '—' : F(d.score,1))}</td><td>${esc(d.confidence == null ? '—' : `${F(d.confidence,1)}%`)}</td><td>${esc(d.change_pct == null ? '—' : `${F(d.change_pct,2)}%`)}</td><td>${esc(d.volatility_regime || d.regime || '—')}</td></tr>`;
    }).join('') || '<tr><td colspan="9">No scan results were returned. Check candle availability and broker market data.</td></tr>';
    tbody.querySelectorAll('tr[data-symbol]').forEach(row => row.addEventListener('click', () => { $('sSymbol').value = row.dataset.symbol; loadSelected(); }));
  }

  async function markets() {
    try {
      const data = await getJson('/analytics/markets/');
      S.markets = data.markets || [];
      $('sSymbol').innerHTML = S.markets.map(m => `<option value="${esc(m.symbol)}">${esc(m.symbol)} · ${esc(m.display_name || m.market || 'Market')}</option>`).join('') || '<option>No active markets</option>';
      if (S.markets.length) await loadSelected(); else status(false, 'No active tradable markets');
    } catch (e) { status(false, e.message); }
  }

  async function loadSelected() {
    const symbol = $('sSymbol').value; if (!symbol) return;
    try {
      const d = await getJson(`/analytics/data/?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent($('sTf').value)}&limit=${$('sLimit').value}`);
      render(d); status(true, `Live · ${d.candles || 0} candles · ${$('sTf').value}`);
    } catch (e) { status(false, e.message); $('sEmpty').hidden = false; }
  }

  async function scan() {
    if (!S.markets.length) return markets();
    const timeframe = $('sTf').value, limit = $('sLimit').value;
    status(true, `Scanning ${S.markets.length} markets…`);
    const results = await Promise.all(S.markets.slice(0, 60).map(async m => {
      try {
        const d = await getJson(`/analytics/data/?symbol=${encodeURIComponent(m.symbol)}&timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`);
        return {...d, display_name: d.display_name || m.display_name, market: d.market || m.market, timeframe};
      } catch (_) { return null; }
    }));
    S.scan = results.filter(Boolean).filter(d => d.signal && String(d.signal).toUpperCase() !== 'HOLD');
    // Keep HOLD/neutral rows visible when no actionable signals exist so the page never falsely reports zero market data.
    if (!S.scan.length) S.scan = results.filter(Boolean);
    renderScan();
    if (S.scan.length) { $('sSymbol').value = S.scan[0].symbol; render(S.scan[0]); }
    status(true, `Live · scanned ${results.filter(Boolean).length} markets · ${S.scan.filter(d => String(d.signal || '').toUpperCase() !== 'HOLD').length} signals`);
  }

  function boot() {
    $('sRefresh')?.addEventListener('click', loadSelected); $('sScan')?.addEventListener('click', scan); $('sAnalyze')?.addEventListener('click', loadSelected);
    $('sSymbol')?.addEventListener('change', loadSelected); $('sTf')?.addEventListener('change', loadSelected); $('sLimit')?.addEventListener('change', loadSelected);
    window.addEventListener('resize', () => { if (S.selected) renderChart(S.selected); });
    window.addEventListener('algobot:account-synced', () => { markets(); });
    markets();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true}); else boot();
})();
