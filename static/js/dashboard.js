(() => {
  'use strict';
  if (window.__algoBotDashboard) return;
  window.__algoBotDashboard = true;
  const $=s=>document.querySelector(s);
  const list=v=>window.AlgoBotFrontendData?.list(v)||(Array.isArray(v)?v:[]);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const money=v=>v==null||v===''||Number.isNaN(Number(v))?'Unavailable':Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
  let refreshTimer=null,loading=false;
  const setHtml=(s,h)=>{const n=$(s);if(n)n.innerHTML=h};
  const setText=(s,t)=>{const n=$(s);if(n)n.textContent=t};
  const empty=m=>`<div class="empty-state">${esc(m)}</div>`;
  const state=()=>window.AlgoBotBrokerState?.get()||{};
  const account=()=>state()?.account||null;
  const request=()=>window.AlgoBotFrontendData?.request;

  async function ensureBrokerState(){
    if(typeof window.AlgoBotBrokerSync==='function'){
      try{await window.AlgoBotBrokerSync();}catch(_){}
    }
    return state();
  }

  function renderAccount(s){
    const a=s?.account;
    if(!a){
      ['balance','equity','available','pnl'].forEach(k=>setText(`[data-kpi="${k}"]`,'Unavailable'));
      setText('[data-kpi-state="balance"]',s?.lastError||'No broker account returned by the backend');
      setText('[data-kpi-state="equity"]','Waiting for broker-backed account data');
      return;
    }
    const c=a.currency||'';
    setText('[data-kpi="balance"]',`${c} ${money(a.balance)}`.trim());
    setText('[data-kpi="equity"]',`${c} ${money(a.equity??a.balance)}`.trim());
    setText('[data-kpi="available"]',`${c} ${money(a.free_margin??a.available_margin??a.available)}`.trim());
    setText('[data-kpi="pnl"]',a.net_profit_loss??a.net_pnl??a.profit_loss??a.pnl==null?'Unavailable':`${c} ${money(a.net_profit_loss??a.net_pnl??a.profit_loss??a.pnl)}`.trim());
    setText('[data-kpi-state="balance"]',s?.status==='READY'?'Broker-confirmed account state':`Broker state: ${s?.status||'synchronizing'}`);
    setText('[data-kpi-state="equity"]',s?.status==='DEGRADED'?'Live verification degraded; showing returned account state':'Broker-confirmed equity');
  }

  function renderBroker(s){
    const a=s?.account;
    if(a){
      setHtml('[data-dashboard-brokers]',`<span><b></b>${esc(a.broker?.name||a.broker_name||'Deriv')} · ${esc(a.broker_account_id||a.account_id||a.loginid||'')} · ${esc(s?.status||'READY')}</span>`);
    }else setHtml('[data-dashboard-brokers]',empty(s?.lastError||'No broker account returned by the backend.'));
  }

  async function load(){
    if(loading)return; loading=true; clearTimeout(refreshTimer);
    try{
      const s=await ensureBrokerState();
      renderAccount(s); renderBroker(s);
      if(typeof request()!=='function') throw new Error('Frontend API client is unavailable.');
      const results=await Promise.allSettled([
        request()('/api/positions/open/'),
        request()('/api/orders/'),
        request()('/api/market/snapshots/all_snapshots/'),
        request()('/api/dashboard/signals/?limit=8')
      ]);
      const [positions,orders,markets,signals]=results;
      const pos=positions.status==='fulfilled'?list(positions.value).slice(0,8):[];
      const ord=orders.status==='fulfilled'?list(orders.value).slice(0,8):[];
      const mkt=markets.status==='fulfilled'?list(markets.value).slice(0,8):[];
      const sig=signals.status==='fulfilled'?list(signals.value).slice(0,8):[];
      const msg=(r,ok)=>r.status==='rejected'?(r.reason?.message||'Backend request failed'):ok;
      setHtml('[data-dashboard-positions]',pos.length?pos.map(x=>`<div class="mini-row"><strong>${esc(x.symbol?.symbol||x.symbol||'Market')}</strong><span>${esc(x.direction||x.side||'')}</span><b>${esc(x.profit??x.pnl??x.profit_loss??'Unavailable')}</b></div>`).join(''):empty(msg(positions,'No open positions reported by the backend.')));
      setHtml('[data-dashboard-orders]',ord.length?ord.map(x=>`<div class="mini-row"><strong>${esc(x.symbol?.symbol||x.symbol||'Market')}</strong><span>${esc(x.direction||x.side||'')}</span><b>${esc(x.status||'Unknown')}</b></div>`).join(''):empty(msg(orders,'No orders reported by the backend.')));
      setHtml('[data-dashboard-markets]',mkt.length?mkt.map(x=>`<div class="mini-row"><strong>${esc(x.symbol?.symbol||x.symbol||'Market')}</strong><span>Bid ${esc(x.bid_price??x.bid??'Unavailable')} · Ask ${esc(x.ask_price??x.ask??'Unavailable')}</span><b>${esc(x.price??x.last_price??x.close??'Unavailable')}</b></div>`).join(''):empty(msg(markets,'No market records reported by the backend.')));
      setHtml('[data-dashboard-signals]',sig.length?sig.map(x=>`<div class="signal-row"><strong>${esc(x.symbol?.symbol||x.symbol||'Market')} ${esc(x.direction||x.signal||'HOLD')}</strong><span>${esc(x.strategy?.name||x.strategy||'')}</span><b>${x.confidence!=null?Number(x.confidence).toFixed(0)+'%':'Unavailable'}</b></div>`).join(''):empty(msg(signals,'No recent backend signals reported.')));
      const activity=[...ord.map(x=>({label:x.symbol?.symbol||x.symbol||'Order',meta:x.status,time:x.updated_at||x.created_at})),...sig.map(x=>({label:x.symbol?.symbol||x.symbol||'Signal',meta:x.direction||x.signal,time:x.created_at||x.timestamp}))].slice(0,8);
      setHtml('[data-dashboard-activity]',activity.length?activity.map(x=>`<div class="mini-row"><strong>${esc(x.label)}</strong><span>${esc(x.meta||'')}</span><b>${esc(x.time?new Date(x.time).toLocaleString():'')}</b></div>`).join(''):empty('No recent backend activity.'));
    }catch(e){
      renderAccount({status:'ERROR',lastError:e?.message||'Dashboard update failed'});
      renderBroker({status:'ERROR',lastError:e?.message||'Dashboard update failed'});
      ['[data-dashboard-positions]','[data-dashboard-orders]','[data-dashboard-markets]','[data-dashboard-signals]','[data-dashboard-activity]'].forEach(x=>setHtml(x,empty(e?.message||'Dashboard backend request failed.')));
    }finally{loading=false;if(!document.hidden)refreshTimer=setTimeout(load,30000);}
  }

  async function activateKillSwitch(){
    const s=state();
    if(!s?.account||!window.confirm('Activate the trading kill switch? This should only be used for an emergency stop.'))return;
    const b=$('[data-dashboard-kill-switch]');if(b)b.disabled=true;
    try{await request()('/api/risk/kill-switch/activate/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason:'Dashboard emergency stop'})});window.dispatchEvent(new CustomEvent('algobot:kill-switch-activated'));window.alert('Kill switch activation confirmed by the backend.');}catch(e){window.alert(e?.message||'Kill switch activation failed.')}finally{if(b)b.disabled=false;}
  }

  function boot(){
    window.AlgoBotBrokerState?.subscribe(event=>{renderAccount(event.detail.state);renderBroker(event.detail.state);load();});
    $('[data-dashboard-refresh]')?.addEventListener('click',load);
    $('[data-dashboard-kill-switch]')?.addEventListener('click',activateKillSwitch);
    document.addEventListener('visibilitychange',()=>{if(document.hidden)clearTimeout(refreshTimer);else if(!loading)load()});
    window.addEventListener('beforeunload',()=>clearTimeout(refreshTimer),{once:true});
    load();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();