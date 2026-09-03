(() => {
  'use strict';
  if (window.__algoBotSignalsPage) return;
  window.__algoBotSignalsPage = true;
  const $ = s => document.querySelector(s);
  const list = v => window.AlgoBotFrontendData?.list(v) || [];
  const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'})[c]);
  let rows=[];
  const pct=v=>v==null?'—':`${Number(v).toFixed(1)}%`;
  function render(){
    const q=String($('[data-page-search]')?.value||'').trim().toLowerCase();
    const filtered=rows.filter(r=>!q||[r.symbol,r.direction,r.market_regime,r.strategy,r.was_executed].join(' ').toLowerCase().includes(q));
    const grid=$('[data-signal-grid]');
    if(grid) grid.innerHTML=filtered.slice(0,12).map(r=>{const c=Math.max(0,Math.min(100,Number(r.confidence||0))),direction=String(r.direction||'').toUpperCase(),action=direction==='BUY'||direction==='SELL'?`<a class="btn primary" href="/trading/?symbol=${encodeURIComponent(r.symbol||'')}&direction=${encodeURIComponent(direction)}&signal_id=${encodeURIComponent(r.id||'')}&strategy=${encodeURIComponent(r.strategy||'')}">Prepare ${direction}</a>`:'<span class="btn" aria-disabled="true">No trade direction</span>';return `<article class="signal-card"><div class="signal-card-head"><div><div class="signal-symbol">${esc(r.symbol)}</div><small>${esc(r.strategy||'Strategy signal')}</small></div><strong class="signal-direction">${esc(r.direction||'NEUTRAL')}</strong></div><div class="signal-meta"><div><span>Confidence</span><strong class="signal-confidence">${pct(r.confidence)}</strong></div><div><span>Regime</span><strong>${esc(r.market_regime||'—')}</strong></div><div><span>Entry</span><strong>${esc(r.entry_price??'—')}</strong></div><div><span>Stop / Target</span><strong>${esc(r.stop_loss??'—')} / ${esc(r.take_profit??'—')}</strong></div></div><div class="signal-bar" aria-label="Confidence ${c}%"><span style="width:${c}%"></span></div><div class="signal-actions">${action}${r.was_executed?'<span class="btn">Executed</span>':''}</div></article>`}).join('')||'<div class="panel"><p>No signals match the current search.</p></div>';
    const table=$('[data-page-table]');
    if(!table)return;
    table.querySelector('thead').innerHTML='<tr><th>Symbol</th><th>Direction</th><th>Confidence</th><th>Regime</th><th>Strategy</th><th>Entry</th><th>Stop</th><th>Target</th><th>Executed</th><th>Created</th></tr>';
    table.querySelector('tbody').innerHTML=filtered.map(r=>`<tr><td><strong>${esc(r.symbol)}</strong></td><td>${esc(r.direction||'—')}</td><td>${pct(r.confidence)}</td><td>${esc(r.market_regime||'—')}</td><td>${esc(r.strategy||'—')}</td><td>${esc(r.entry_price??'—')}</td><td>${esc(r.stop_loss??'—')}</td><td>${esc(r.take_profit??'—')}</td><td>${r.was_executed?'Yes':'No'}</td><td>${esc(r.created_at?new Date(r.created_at).toLocaleString():'—')}</td></tr>`).join('')||'<tr class="empty-row"><td colspan="10">No strategy signals returned.</td></tr>';
  }
  async function load(){
    const status=$('[data-page-status]'),count=$('[data-record-count]'),updated=$('[data-page-updated]');
    try{
      if(status)status.textContent='Loading';
      rows=list(await window.AlgoBotFrontendData.request('/api/strategy-signals/?limit=100',{},8000));
      if(count)count.textContent=rows.length;
      const avg=rows.length?rows.reduce((s,r)=>s+Number(r.confidence||0),0)/rows.length:null;
      const conf=$('[data-page-confidence]'); if(conf)conf.textContent=avg==null?'—':pct(avg);
      const executed=$('[data-page-executed]'); if(executed)executed.textContent=rows.filter(r=>r.was_executed).length;
      if(updated)updated.textContent=new Date().toLocaleTimeString();
      if(status)status.textContent='Ready'; render();
    }catch(e){rows=[];if(status)status.textContent='Unavailable';if(count)count.textContent='—';render();}
  }
  function boot(){ $('[data-page-search]')?.addEventListener('input',render); window.addEventListener('algobot:account-synced',load); load(); }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
