/* Phase 2 terminal context controls: preview, market context and mobile-safe state. */
(() => {
  'use strict';
  const $=(s,r=document)=>r.querySelector(s);
  const api=(url,o={},t=10000)=>window.AlgoBotFrontendData?.request(url,o,t);
  const esc=v=>String(v??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[c]));
  async function preview(){
    const account=$('#account')?.value,symbol=$('#symbol')?.value,direction=document.querySelector('[data-direction].active')?.dataset.direction||'BUY',stake=$('[name="stake"]')?.value||'1',orderType=$('[name="order_type"]')?.value||'market',strategy=$('[name="strategy"]')?.value||'';
    const target=$('[data-order-preview]'); if(!target)return;
    target.hidden=false; target.textContent='Running authoritative pre-trade checks…';
    if(!account||!symbol){target.textContent='Select a connected broker account and instrument first.';return;}
    try{
      const data=await api('/api/orders/preview/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({broker_account:Number(account),symbol,direction,order_type:orderType,stake,strategy})},15000);
      target.innerHTML=`<strong>${esc(data.status==='ready'?'READY TO SUBMIT':'REJECTED')}</strong><div>${esc(data.account?.broker||'Broker')} · ${esc(data.account?.account_id||'')} · ${esc(data.account?.environment||'')}</div><div>Bid ${esc(data.market?.bid??'—')} · Ask ${esc(data.market?.ask??'—')} · Spread ${esc(data.market?.spread??'—')}</div><div>Fresh market data: ${data.gates?.fresh_market_data?'YES':'NO'} · Environment verified: ${data.gates?.environment_verified?'YES':'NO'}</div>`;
    }catch(e){target.textContent=`Pre-trade preview rejected: ${e.message||'request failed'}`;}
  }
  function context(){
    const terminal=$('.terminal-page'); if(!terminal)return;
    const ticket=$('.order-ticket'); if(ticket&&!$('[data-order-preview]',ticket)){
      const button=document.createElement('button');button.type='button';button.className='btn ghost';button.textContent='Preview order';button.dataset.orderPreviewButton='';ticket.querySelector('[data-order-form]')?.insertBefore(button,ticket.querySelector('.execute-btn'));button.addEventListener('click',preview);
      const box=document.createElement('div');box.className='order-preview';box.dataset.orderPreview='';box.hidden=true;ticket.appendChild(box);
    }
    document.querySelectorAll('[data-chart-mode],[data-chart-action]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('[data-chart-mode]').forEach(x=>x.classList.toggle('active',x===b));}));
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',context,{once:true});else context();
})();
