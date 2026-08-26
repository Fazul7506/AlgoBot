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
  const state=()=>window.AlgoBotBrokerState?.get();
  const connected=()=>{const s=state();return !!s?.account&&['CONNECTED','SYNCING','READY'].includes(s.status)};

  async function ensureBrokerState(){
    if(connected()) return state();
    // The canonical bridge owns broker discovery/synchronization. Never start
    // a second account GET + sync sequence from this page.
    if(typeof window.AlgoBotBrokerSync==='function') await window.AlgoBotBrokerSync();
    return state();
  }
  function renderAccount(s){
    const a=s?.account,live=!!a&&connected();
    if(!live){
      setText('[data-kpi="balance"]','Unavailable');setText('[data-kpi="equity"]','Unavailable');setText('[data-kpi="available"]','Unavailable');
      const reason=s?.lastError||(s?.status==='NO_BROKER'?'No canonical broker account is available.':`Broker state: ${s?.status||'unknown'}`);
      setText('[data-kpi-state="balance"]',reason);setText('[data-kpi-state="equity"]',s?.status==='DEGRADED'?'Live broker verification failed; last known account is retained.':'Waiting for broker confirmation');return;
    }
    const c=a.currency||'';setText('[data-kpi="balance"]',`${c} ${money(a.balance)}`.trim());setText('[data-kpi="equity"]',`${c} ${money(a.equity)}`.trim());setText('[data-kpi="available"]',`${c} ${money(a.free_margin??a.available_margin)}`.trim());
    setText('[data-kpi-state="balance"]',s.status==='READY'?'Broker-confirmed account state':'Synchronizing broker state');setText('[data-kpi-state="equity"]',s.status==='READY'?'Broker-confirmed equity':'Synchronizing broker state');
  }
  function renderDisconnected(s){
    const status=s?.status||'NO_BROKER',m=status==='NO_BROKER'?'No broker account is available from the backend.':status==='DEGRADED'?`Broker connection degraded: ${s?.lastError||'live verification failed'}`:status==='ERROR'?`Broker connection error: ${s?.lastError||'verification failed'}`:'Broker data is unavailable until the live connection is restored.';
    ['[data-dashboard-positions]','[data-dashboard-orders]','[data-dashboard-markets]','[data-dashboard-signals]','[data-dashboard-activity]'].forEach(x=>setHtml(x,empty(m)));
    setHtml('[data-dashboard-brokers]',`<span><b class="danger"></b>${esc(m)}</span>`);
  }
  async function load(){
    if(loading)return;loading=true;clearTimeout(refreshTimer);
    try{
      const s=await ensureBrokerState();renderAccount(s);
      if(!connected()){renderDisconnected(s);return;}
      const request=window.AlgoBotFrontendData.request;
      const [positions,orders,markets,signals]=await Promise.allSettled([
        request('/api/positions/open/'),request('/api/orders/'),request('/api/market/snapshots/all_snapshots/'),request('/api/dashboard/signals/?limit=8')
      ]);
      const pos=positions.status==='fulfilled'?list(positions.value).slice(0,8):[],ord=orders.status==='fulfilled'?list(orders.value).slice(0,8):[],mkt=markets.status==='fulfilled'?list(markets.value).slice(0,8):[],sig=signals.status==='fulfilled'?list(signals.value).slice(0,8):[];
      const unavailable=r=>r.status==='rejected'?'This card could not be loaded. Refresh to try again.':null;
      setHtml('[data-dashboard-positions]',pos.length?pos.map(x=>`<div class="mini-row"><strong>${esc(x.symbol)}</strong><span>${esc(x.direction||x.side||'')}</span><b>${esc(x.profit??x.pnl??x.profit_loss??'Unavailable')}</b></div>`).join(''):empty(unavailable(positions)||'No open positions reported by the backend.'));
      setHtml('[data-dashboard-orders]',ord.length?ord.map(x=>`<div class="mini-row"><strong>${esc(x.symbol)}</strong><span>${esc(x.direction||x.side||'')}</span><b>${esc(x.status||'Unknown')}</b></div>`).join(''):empty(unavailable(orders)||'No orders reported by the backend.'));
      setHtml('[data-dashboard-signals]',sig.length?sig.map(x=>`<div class="signal-row"><strong>${esc(x.symbol)} ${esc(x.direction||x.signal||'HOLD')}</strong><span>${esc(x.strategy||'')}</span><b>${x.confidence!=null?Number(x.confidence).toFixed(0)+'%':'Unavailable'}</b></div>`).join(''):empty(unavailable(signals)||'No recent backend signals reported.'));
      setHtml('[data-dashboard-markets]',mkt.length?mkt.map(x=>`<div class="mini-row"><strong>${esc(x.symbol?.symbol||x.symbol||'Market')}</strong><span>Bid ${esc(x.bid_price??x.bid??'Unavailable')} · Ask ${esc(x.ask_price??x.ask??'Unavailable')}</span><b>${esc(x.price??x.last_price??'Unavailable')}</b></div>`).join(''):empty(unavailable(markets)||'No market data reported by the backend.'));
      const a=state()?.account;setHtml('[data-dashboard-brokers]',a?`<span><b></b>${esc(a.broker?.name||a.broker_name||'Broker')} · ${esc(a.broker_account_id||a.account_id||'')} · ${esc(state()?.status||'READY')}</span>`:empty('No connected broker account'));
      const activity=[...ord.map(x=>({label:x.symbol,meta:x.status,time:x.updated_at||x.created_at})),...sig.map(x=>({label:x.symbol,meta:x.direction||x.signal,time:x.created_at||x.timestamp}))].slice(0,8);
      setHtml('[data-dashboard-activity]',activity.length?activity.map(x=>`<div class="mini-row"><strong>${esc(x.label)}</strong><span>${esc(x.meta||'')}</span><b>${esc(x.time?new Date(x.time).toLocaleString():'')}</b></div>`).join(''):empty('No recent backend activity.'));
    }catch(e){renderDisconnected({status:'ERROR',lastError:e?.message||'Dashboard update failed'});}finally{loading=false;if(!document.hidden)refreshTimer=setTimeout(load,30000);}
  }
  async function activateKillSwitch(){
    if(!connected()||!window.confirm('Activate the trading kill switch? This should only be used for an emergency stop.'))return;
    const b=$('[data-dashboard-kill-switch]');if(b)b.disabled=true;
    try{await window.AlgoBotFrontendData.request('/api/risk/kill-switch/activate/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason:'Dashboard emergency stop'})});window.dispatchEvent(new CustomEvent('algobot:kill-switch-activated'));window.alert('Kill switch activation confirmed by the backend.');}catch(e){window.alert(e.message)}finally{if(b)b.disabled=false;}
  }
  function boot(){
    window.AlgoBotBrokerState?.subscribe(event=>{renderAccount(event.detail.state);if(connected())load();else renderDisconnected(event.detail.state)});
    $('[data-dashboard-refresh]')?.addEventListener('click',()=>load());$('[data-dashboard-kill-switch]')?.addEventListener('click',activateKillSwitch);
    document.addEventListener('visibilitychange',()=>{if(document.hidden)clearTimeout(refreshTimer);else if(!loading)load()});
    window.addEventListener('beforeunload',()=>clearTimeout(refreshTimer),{once:true});load();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
