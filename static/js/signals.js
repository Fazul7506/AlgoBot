(() => {
  'use strict';
  if (window.__algoBotSignalsPage) return;
  window.__algoBotSignalsPage = true;
  const $ = s => document.querySelector(s);
  const list = v => window.AlgoBotFrontendData?.list(v) || [];
  const esc = v => String(v ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const val = (r, ...keys) => keys.map(k => r?.[k]).find(v => v !== undefined && v !== null && v !== '') ?? '—';
  const pct = v => v === '—' ? '—' : `${Number(v).toFixed(1)}%`;
  const age = v => { const d = new Date(v); if (!v || Number.isNaN(d.getTime())) return '—'; const s = Math.max(0, Math.floor((Date.now()-d.getTime())/1000)); return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.floor(s/60)}m ago` : `${Math.floor(s/3600)}h ago`; };
  const pick = (r, ...keys) => val(r, ...keys);
  const section = (title, items) => `<section class="signal-detail-section"><h3>${esc(title)}</h3><div class="signal-detail-grid">${items.map(([k,...keys]) => `<div class="signal-detail-item"><span>${esc(k)}</span><strong>${esc(pick(current,...keys))}</strong></div>`).join('')}</div></section>`;
  const statusOf = r => String(val(r,'trigger_status','status','confirmation_status')).toLowerCase().replace(/[_-]+/g,' ');
  const labelOf = r => { const s=statusOf(r); if (['confirmed','triggered','entry condition met','ready'].includes(s)) return ['CONFIRMED SIGNAL','confirmed']; if (['waiting','pending','waiting for confirmation','setup detected'].includes(s)) return ['SETUP DETECTED — WAIT','waiting']; return ['NO TRADE — CONFIRMATION FAILED','blocked']; };
  let rows = [], current = {};
  function details(r) {
    current = r;
    const metadata = r.metadata || {};
    const read = (...keys) => val(r,...keys) !== '—' ? val(r,...keys) : val(metadata,...keys);
    const groups = [
      ['Market context', [['Instrument','display_name','instrument','symbol'],['Broker symbol','symbol','instrument'],['Timeframe','timeframe','interval'],['Price','price','current_price','last_price'],['Signal','direction','signal_type'],['Score','score','signal_score'],['Confidence','confidence','signal_confidence'],['Market regime','market_regime','regime']]],
      ['Key levels', [['Resistance','resistance','key_levels.resistance'],['Support','support','key_levels.support'],['Range','range','key_levels.range'],['Change','change','price_change','change_percent']]],
      ['Trend', [['SMA 20','sma20','sma_20'],['SMA 50','sma50','sma_50'],['SMA 200','sma200','sma_200'],['EMA 9','ema9','ema_9'],['EMA 21','ema21','ema_21'],['Trend confirmation','trend_confirmation','trend']]],
      ['Momentum & volatility', [['RSI 14','rsi14','rsi_14','rsi'],['ATR 14','atr14','atr_14','atr'],['MACD histogram','macd_histogram','macd_hist'],['Bollinger width','bollinger_width','bb_width'],['Volatility regime','volatility_regime','volatility']]],
      ['Smart money & price action', [['Market structure','market_structure'],['Liquidity sweeps','liquidity_sweeps','liquidity_sweep'],['Fair value gaps','fair_value_gaps','fvg'],['Supply / demand','supply_demand'],['Candlestick patterns','candlestick_patterns','patterns'],['Fibonacci','fibonacci'],['Confluence','confluence']]],
      ['Execution & evidence', [['Entry condition','entry_condition','entry'],['Risk gate','risk_gate','risk_status'],['Trend confirmation','trend_confirmation','trend'],['Momentum confirmation','momentum_confirmation','momentum'],['Data freshness','data_freshness','data_status'],['Broker availability','broker_availability','execution_availability'],['Confirmation','confirmation','confirmation_reason'],['Reason','reason','evidence','explanation']]]
    ];
    return groups.map(([title, items]) => `<section class="signal-detail-section"><h3>${esc(title)}</h3><div class="signal-detail-grid">${items.map(([label,...keys]) => `<div class="signal-detail-item"><span>${esc(label)}</span><strong>${esc(read(...keys))}</strong></div>`).join('')}</div></section>`).join('');
  }
  function render(){
    const q=String($('[data-page-search]')?.value||'').trim().toLowerCase();
    const filtered=rows.filter(r=>!q||JSON.stringify(r).toLowerCase().includes(q));
    const grid=$('[data-signal-grid]');
    if(grid) grid.innerHTML=filtered.slice(0,12).map(r=>{ const c=Math.max(0,Math.min(100,Number(val(r,'confidence'))||0)); const direction=String(val(r,'direction','signal_type')).toUpperCase(); const [state,kind]=labelOf(r); const executable=kind==='confirmed'&&(direction==='BUY'||direction==='SELL'); const action=executable?`<a class="btn primary" href="/trading/?symbol=${encodeURIComponent(val(r,'symbol'))}&direction=${encodeURIComponent(direction)}&signal_id=${encodeURIComponent(val(r,'id'))}">Prepare ${esc(direction)}</a>`:'<span class="btn" aria-disabled="true">DO NOT TRADE</span>'; return `<article class="signal-card signal-${kind}"><div class="signal-card-head"><div><div class="signal-symbol">${esc(val(r,'display_name','instrument','symbol'))}</div><small>${esc(val(r,'symbol'))} · ${esc(val(r,'timeframe','interval'))}</small></div><strong class="signal-state">${esc(state)}</strong></div><div class="signal-hero-grid"><div><span>Price</span><strong>${esc(val(r,'price','current_price','last_price'))}</strong></div><div><span>Direction</span><strong>${esc(direction)}</strong></div><div><span>Score</span><strong>${esc(val(r,'score','signal_score'))}</strong></div><div><span>Confidence</span><strong class="signal-confidence">${pct(val(r,'confidence'))}</strong></div></div><div class="signal-bar" aria-label="Confidence ${c}%"><span style="width:${c}%"></span></div><div class="signal-detail-panel">${details(r)}</div><div class="signal-actions">${action}<span class="btn">${esc(val(r,'strategy','strategy_name'))}</span></div><small class="signal-timestamp">Updated ${esc(age(val(r,'created_at','timestamp')))}</small></article>`; }).join('')||'<div class="panel"><p>No live signals match the current search.</p></div>';
    const table=$('[data-page-table]'); if(!table)return; const cols=['Instrument','Timeframe','Price','Signal','Score','Confidence','Regime','Status','Updated']; table.querySelector('thead').innerHTML=`<tr>${cols.map(c=>`<th>${c}</th>`).join('')}</tr>`; table.querySelector('tbody').innerHTML=filtered.map(r=>{const [state]=labelOf(r);return `<tr><td><strong>${esc(val(r,'display_name','instrument','symbol'))}</strong><br><small>${esc(val(r,'symbol'))}</small></td><td>${esc(val(r,'timeframe','interval'))}</td><td>${esc(val(r,'price','current_price','last_price'))}</td><td>${esc(val(r,'direction','signal_type'))}</td><td>${esc(val(r,'score','signal_score'))}</td><td>${pct(val(r,'confidence'))}</td><td>${esc(val(r,'market_regime','regime'))}</td><td>${esc(state)}</td><td>${esc(age(val(r,'created_at','timestamp')))}</td></tr>`}).join('')||'<tr><td colspan="9">No live strategy signals returned.</td></tr>';
  }
  async function load(){ try { const status=$('[data-page-status]'); if(status) status.innerHTML='<span class="signal-live-dot"></span>Syncing live feed…'; rows=list(await window.AlgoBotFrontendData.request('/api/strategy-signals/?limit=100',{},8000)); $('[data-record-count]').textContent=rows.length; const avg=rows.length?rows.reduce((s,r)=>s+Number(val(r,'confidence')||0),0)/rows.length:null; $('[data-page-confidence]').textContent=avg==null?'—':pct(avg); $('[data-page-executed]').textContent=rows.filter(r=>r.was_executed).length; if(status) status.innerHTML=`<span class="signal-live-dot"></span>Live · ${new Date().toLocaleTimeString()}`; render(); } catch(e) { rows=[]; if($('[data-page-status]')) $('[data-page-status]').textContent='Feed unavailable'; render(); } }
  function boot(){ $('[data-page-search]')?.addEventListener('input',render); window.addEventListener('algobot:account-synced',load); load(); window.setInterval(load,5000); }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',boot,{once:true}); else boot();
})();
