(() => {
  'use strict';
  if (window.__algoBotSignalsPage) return;
  window.__algoBotSignalsPage = true;
  const $ = s => document.querySelector(s);
  const list = v => window.AlgoBotFrontendData?.list(v) || [];
  const esc = v => String(v ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const val = (r, ...keys) => keys.map(k => r?.[k]).find(v => v !== undefined && v !== null && v !== '') ?? '—';
  const pct = v => v === '—' ? '—' : `${Number(v).toFixed(1)}%`;
  const statusOf = r => String(val(r,'trigger_status','status','confirmation_status')).toLowerCase().replace(/[_-]+/g,' ');
  const labelOf = r => { const s=statusOf(r); if (['confirmed','triggered','entry condition met','ready'].includes(s)) return ['CONFIRMED SIGNAL','confirmed']; if (['waiting','pending','waiting for confirmation','setup detected'].includes(s)) return ['SETUP DETECTED — WAIT','waiting']; return ['NO TRADE — CONFIRMATION FAILED','blocked']; };
  let rows = [];
  function render(){
    const q=String($('[data-page-search]')?.value||'').trim().toLowerCase();
    const filtered=rows.filter(r=>!q||Object.values(r||{}).join(' ').toLowerCase().includes(q));
    const grid=$('[data-signal-grid]');
    if(grid) grid.innerHTML=filtered.slice(0,12).map(r=>{
      const c=Math.max(0,Math.min(100,Number(val(r,'confidence','signal_confidence'))||0)), direction=String(val(r,'direction','signal_type')).toUpperCase();
      const [state,kind]=labelOf(r), executable=kind==='confirmed'&&(direction==='BUY'||direction==='SELL');
      const action=executable?`<a class="btn primary" href="/trading/?symbol=${encodeURIComponent(val(r,'symbol'))}&direction=${encodeURIComponent(direction)}&signal_id=${encodeURIComponent(val(r,'id'))}&strategy=${encodeURIComponent(val(r,'strategy'))}">Prepare ${esc(direction)}</a>`:'<span class="btn" aria-disabled="true">DO NOT TRADE</span>';
      const evidence=val(r,'evidence','reason','explanation','acceptance_reason'), sequence=val(r,'digit_sequence','recent_digits','sequence'), confirmation=val(r,'confirmation_sequence','confirmation_reason','confirmation');
      return `<article class="signal-card signal-${kind}"><div class="signal-card-head"><div><div class="signal-symbol">${esc(val(r,'display_name','symbol','instrument'))}</div><small>${esc(val(r,'contract_type','signal_type','strategy'))}</small></div><strong class="signal-state">${esc(state)}</strong></div><div class="signal-meta"><div><span>Direction</span><strong>${esc(direction)}</strong></div><div><span>Confidence</span><strong class="signal-confidence">${pct(val(r,'confidence','signal_confidence'))}</strong></div><div><span>Market regime</span><strong>${esc(val(r,'market_regime','regime'))}</strong></div><div><span>Entry / validity</span><strong>${esc(val(r,'entry_condition','entry_price'))} / ${esc(val(r,'validity_window','expires_at'))}</strong></div><div><span>Recent sequence</span><strong>${esc(sequence)}</strong></div><div><span>Risk gate</span><strong>${esc(val(r,'risk_gate','risk_status','risk_assessment'))}</strong></div><div><span>Trend / momentum</span><strong>${esc(val(r,'trend_confirmation','trend'))} / ${esc(val(r,'momentum_confirmation','momentum'))}</strong></div><div><span>Data / broker</span><strong>${esc(val(r,'data_freshness','data_status'))} / ${esc(val(r,'broker_availability','execution_availability'))}</strong></div></div><div class="signal-evidence"><b>Why this state</b><p>${esc(evidence)}</p><b>Confirmation</b><p>${esc(confirmation)}</p></div><div class="signal-bar" aria-label="Confidence ${c}%"><span style="width:${c}%"></span></div><div class="signal-actions">${action}<span class="btn">${esc(val(r,'model','strategy','strategy_name'))}</span></div><small class="signal-timestamp">${esc(val(r,'created_at','timestamp','signal_age'))}</small></article>`;
    }).join('')||'<div class="panel"><p>No signals match the current search.</p></div>';
    const table=$('[data-page-table]'); if(!table)return;
    const cols=['Instrument','State','Direction','Confidence','Regime','Entry condition','Risk gate','Reason','Freshness','Created'];
    table.querySelector('thead').innerHTML=`<tr>${cols.map(c=>`<th>${c}</th>`).join('')}</tr>`;
    table.querySelector('tbody').innerHTML=filtered.map(r=>{const [state]=labelOf(r);return `<tr><td><strong>${esc(val(r,'display_name','symbol','instrument'))}</strong></td><td>${esc(state)}</td><td>${esc(val(r,'direction','signal_type'))}</td><td>${pct(val(r,'confidence','signal_confidence'))}</td><td>${esc(val(r,'market_regime','regime'))}</td><td>${esc(val(r,'entry_condition','entry_price'))}</td><td>${esc(val(r,'risk_gate','risk_status'))}</td><td>${esc(val(r,'reason','explanation','evidence'))}</td><td>${esc(val(r,'data_freshness','data_status'))}</td><td>${esc(val(r,'created_at','timestamp'))}</td></tr>`}).join('')||'<tr><td colspan="10">No strategy signals returned.</td></tr>';
  }
  async function load(){try{const status=$('[data-page-status]');if(status)status.textContent='Loading';rows=list(await window.AlgoBotFrontendData.request('/api/strategy-signals/?limit=100',{},8000));$('[data-record-count]').textContent=rows.length;const avg=rows.length?rows.reduce((s,r)=>s+Number(val(r,'confidence','signal_confidence')||0),0)/rows.length:null;$('[data-page-confidence]').textContent=avg==null?'—':pct(avg);$('[data-page-executed]').textContent=rows.filter(r=>r.was_executed).length;if(status)status.textContent='Ready';render()}catch(e){rows=[];if($('[data-page-status]'))$('[data-page-status]').textContent='Unavailable';render()}}
  function boot(){ $('[data-page-search]')?.addEventListener('input',render);window.addEventListener('algobot:account-synced',load);load(); }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
