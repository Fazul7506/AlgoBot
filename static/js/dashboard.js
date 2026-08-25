(() => {
  'use strict';
  if (window.__algoBotDashboard) return;
  window.__algoBotDashboard = true;

  const $ = selector => document.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || (Array.isArray(value) ? value : []);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const money = value => value == null || value === '' || Number.isNaN(Number(value)) ? 'Unavailable' : Number(value).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
  let refreshTimer = null;
  let loading = false;
  const request = (url, options) => window.AlgoBotFrontendData.request(url, options, 5500);

  const setHtml = (selector, html) => { const node=$(selector); if(node) node.innerHTML=html; };
  const setText = (selector, text) => { const node=$(selector); if(node) node.textContent=text; };
  const empty = message => `<div class="empty-state">${esc(message)}</div>`;

  // DEGRADED/ERROR must never be treated as a live broker connection. This
  // prevents stale database values from being presented as live broker data.
  function connected() {
    const state=window.AlgoBotBrokerState?.get();
    return !!state?.account && ['CONNECTED','SYNCING','READY'].includes(state.status);
  }

  function renderAccount(state) {
    const account=state?.account;
    const live=!!account && connected();
    if(!live) {
      setText('[data-kpi="balance"]','Unavailable');
      setText('[data-kpi="equity"]','Unavailable');
      setText('[data-kpi="available"]','Unavailable');
      const reason=state?.lastError || (state?.status==='NO_BROKER' ? 'No canonical broker account is available.' : `Broker state: ${state?.status || 'unknown'}`);
      setText('[data-kpi-state="balance"]',reason);
      setText('[data-kpi-state="equity"]',state?.status==='DEGRADED' ? 'Live broker verification failed; stale values are hidden.' : 'Waiting for broker confirmation');
      return;
    }
    const currency=account.currency || '';
    setText('[data-kpi="balance"]',`${currency} ${money(account.balance)}`.trim());
    setText('[data-kpi="equity"]',`${currency} ${money(account.equity)}`.trim());
    setText('[data-kpi="available"]',`${currency} ${money(account.free_margin ?? account.available_margin)}`.trim());
    setText('[data-kpi-state="balance"]',state.status==='READY'?'Broker-confirmed account state':'Synchronizing broker state');
    setText('[data-kpi-state="equity"]',state.status==='READY'?'Broker-confirmed equity':'Synchronizing broker state');
  }

  function renderDisconnected(state) {
    const status=state?.status || 'NO_BROKER';
    const message=status==='NO_BROKER' ? 'No broker account is available from the backend.' : status==='DEGRADED' ? `Broker connection degraded: ${state?.lastError || 'live verification failed'}` : status==='ERROR' ? `Broker connection error: ${state?.lastError || 'verification failed'}` : 'Broker data is unavailable until the live connection is restored.';
    setHtml('[data-dashboard-positions]',empty(message));
    setHtml('[data-dashboard-orders]',empty(message));
    setHtml('[data-dashboard-markets]',empty(message));
    setHtml('[data-dashboard-signals]',empty(message));
    setHtml('[data-dashboard-activity]',empty(message));
    setHtml('[data-dashboard-brokers]',`<span><b class="danger"></b>${esc(message)}</span>`);
  }

  async function load() {
    if(loading) return;
    loading=true;
    clearTimeout(refreshTimer);
    const state=window.AlgoBotBrokerState?.get();
    renderAccount(state);
    if(!connected()) { renderDisconnected(state); loading=false; return; }
    try {
      // Dashboard cards are independent.  A slow market or signal endpoint
      // must not hold the entire page hostage, so cap each request and render
      // the completed cards as soon as the batch settles.
      const [positions,orders,markets,signals]=await Promise.allSettled([
        request('/api/positions/open/'),
        request('/api/orders/'),
        request('/api/market/snapshots/all_snapshots/'),
        request('/api/dashboard/signals/?limit=8')
      ]);
      const pos=positions.status==='fulfilled'?list(positions.value).slice(0,8):[];
      const ord=orders.status==='fulfilled'?list(orders.value).slice(0,8):[];
      const mkt=markets.status==='fulfilled'?list(markets.value).slice(0,8):[];
      const sig=signals.status==='fulfilled'?list(signals.value).slice(0,8):[];
      const unavailable = result => result.status==='rejected' ? 'This card could not be loaded. Refresh to try again.' : null;
      setHtml('[data-dashboard-positions]',pos.length?pos.map(x=>`<div class="mini-row"><strong>${esc(x.symbol)}</strong><span>${esc(x.direction||x.side||'')}</span><b>${esc(x.profit??x.pnl??x.profit_loss??'Unavailable')}</b></div>`).join(''):empty(unavailable(positions)||'No open positions reported by the backend.'));
      setHtml('[data-dashboard-orders]',ord.length?ord.map(x=>`<div class="mini-row"><strong>${esc(x.symbol)}</strong><span>${esc(x.direction||x.side||'')}</span><b>${esc(x.status||'Unknown')}</b></div>`).join(''):empty(unavailable(orders)||'No orders reported by the backend.'));
      setHtml('[data-dashboard-signals]',sig.length?sig.map(x=>`<div class="signal-row"><strong>${esc(x.symbol)} ${esc(x.direction||x.signal||'HOLD')}</strong><span>${esc(x.strategy||'')}</span><b>${x.confidence!=null?Number(x.confidence).toFixed(0)+'%':'Unavailable'}</b></div>`).join(''):empty(unavailable(signals)||'No recent backend signals reported.'));
      setHtml('[data-dashboard-markets]',mkt.length?mkt.map(x=>`<div class="mini-row"><strong>${esc(x.symbol?.symbol||x.symbol||'Market')}</strong><span>Bid ${esc(x.bid_price??x.bid??'Unavailable')} · Ask ${esc(x.ask_price??x.ask??'Unavailable')}</span><b>${esc(x.price??x.last_price??'Unavailable')}</b></div>`).join(''):empty(unavailable(markets)||'No market data reported by the backend.'));
      const account=state?.account;
      setHtml('[data-dashboard-brokers]',account?`<span><b></b>${esc(account.broker?.name||account.broker_name||'Broker')} · ${esc(account.broker_account_id||account.account_id)} · ${state.status}</span>`:empty('No connected broker account'));
      const activity=[...ord.map(x=>({label:x.symbol,meta:x.status,time:x.updated_at||x.created_at})),...sig.map(x=>({label:x.symbol,meta:x.direction||x.signal,time:x.created_at||x.timestamp}))].slice(0,8);
      setHtml('[data-dashboard-activity]',activity.length?activity.map(x=>`<div class="mini-row"><strong>${esc(x.label)}</strong><span>${esc(x.meta||'')}</span><b>${esc(x.time?new Date(x.time).toLocaleString():'')}</b></div>`).join(''):empty('No recent backend activity.'));
    } catch (error) {
      // A rendering/runtime error must release the refresh lock too.  Without
      // this, one malformed payload leaves the Refresh button appearing stuck.
      renderDisconnected({status:'ERROR',lastError:error?.message || 'Dashboard update failed'});
    } finally {
      loading=false;
      if (!document.hidden) refreshTimer=setTimeout(load,30000);
    }
  }

  async function activateKillSwitch() {
    if(!connected()) return;
    if(!window.confirm('Activate the trading kill switch? This should only be used for an emergency stop.')) return;
    const button=$('[data-dashboard-kill-switch]'); if(button) button.disabled=true;
    try {
      await window.AlgoBotFrontendData.request('/api/risk/kill-switch/activate/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason:'Dashboard emergency stop'})});
      window.dispatchEvent(new CustomEvent('algobot:kill-switch-activated')); window.alert('Kill switch activation confirmed by the backend.');
    } catch(error) { window.alert(error.message); }
    finally { if(button) button.disabled=false; }
  }

  function boot() {
    window.AlgoBotBrokerState?.subscribe(event=>{ renderAccount(event.detail.state); if(connected()) load(); else renderDisconnected(event.detail.state); });
    $('[data-dashboard-refresh]')?.addEventListener('click',load);
    $('[data-dashboard-kill-switch]')?.addEventListener('click',activateKillSwitch);
    document.addEventListener('visibilitychange',()=>{
      if (document.hidden) clearTimeout(refreshTimer);
      else if (!loading) load();
    });
    window.addEventListener('beforeunload',()=>clearTimeout(refreshTimer),{once:true});
    load();
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',boot,{once:true}); else boot();
})();
