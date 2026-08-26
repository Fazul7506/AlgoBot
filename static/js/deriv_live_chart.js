/* Live broker chart with account-driven readiness and bounded recovery. */
(() => {
  'use strict';
  if (window.__algoBotLiveChart) return;
  window.__algoBotLiveChart = true;
  const $ = s => document.querySelector(s);
  const list = v => window.AlgoBotFrontendData?.list(v) || [];
  const safe = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const money = v => Number.isFinite(Number(v)) ? Number(v).toLocaleString(undefined,{maximumFractionDigits:8}) : 'Unavailable';
  const api = (u,o={},t=10000) => window.AlgoBotFrontendData.request(u,o,t);
  const wsUrl = () => `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/market-data/`;
  let ws=null, reconnect=null, symbol='', mode='ticks', points=[], candles=[], caps=null, closed=false;

  const accountReady = () => {
    const state = window.AlgoBotBrokerState?.get();
    return !!(window.AlgoBotBrokerAccounts?.length || state?.account);
  };
  const updateInsights = (values, structure) => {
    if (!values.length) return;
    const first=values[0], last=values.at(-1);
    $('[data-trend]')?.replaceChildren(document.createTextNode(last >= first ? 'Bullish' : 'Bearish'));
    const mean=values.reduce((a,b)=>a+b,0)/values.length;
    const variance=values.reduce((a,b)=>a+(b-mean)**2,0)/values.length;
    $('[data-volatility]')?.replaceChildren(document.createTextNode(money(Math.sqrt(variance))));
    $('[data-structure]')?.replaceChildren(document.createTextNode(structure));
    $('[data-chart-loading]')?.replaceChildren(document.createTextNode(`Live broker data · ${values.length} points`));
  };
  const renderTicks = () => {
    const chart=$('#chart'); if(!chart || points.length<2) return;
    const W=1000,H=330,P=18,v=points.map(p=>p.price),min=Math.min(...v),max=Math.max(...v),span=max-min||Math.max(Math.abs(max)*.0001,1);
    const coords=points.map((p,i)=>`${(P+i/Math.max(1,points.length-1)*(W-P*2)).toFixed(1)},${(H-P-(p.price-min)/span*(H-P*2)).toFixed(1)}`).join(' ');
    chart.innerHTML=`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:100%;display:block"><polyline points="${coords}" fill="none" stroke="currentColor" stroke-width="2.5"/><text x="${W-P}" y="${P+2}" text-anchor="end" fill="currentColor" opacity=".7" font-size="13">LIVE ${safe(money(v.at(-1)))}</text></svg>`;
    updateInsights(v,'Tick stream');
  };
  const renderCandles = () => {
    const chart=$('#chart'); if(!chart || !candles.length) return;
    const W=1000,H=330,P=18,hi=candles.map(c=>c.high),lo=candles.map(c=>c.low),max=Math.max(...hi),min=Math.min(...lo),span=max-min||1,step=(W-P*2)/candles.length,w=Math.max(2,Math.min(14,step*.62)),y=x=>H-P-(Number(x)-min)/span*(H-P*2);
    const parts=candles.map((c,i)=>{const x=P+i*step+step/2,o=+c.open,cl=+c.close,h=+c.high,l=+c.low,up=cl>=o,s=up?'currentColor':'currentColor';return `<line x1="${x}" y1="${y(h)}" x2="${x}" y2="${y(l)}" stroke="${s}" stroke-width="1.5" opacity="${up?'.9':'.55'}"/><rect x="${x-w/2}" y="${y(Math.max(o,cl))}" width="${w}" height="${Math.max(1,Math.abs(y(o)-y(cl)))}" fill="${s}" opacity=".65"/>`;}).join('');
    chart.innerHTML=`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:100%;display:block">${parts}</svg>`;
    updateInsights(candles.map(c=>c.close),'Broker candlestick stream');
  };
  function renderCaps(data){
    caps=data||{}; const tf=Array.isArray(caps.timeframes)?caps.timeframes:[], select=$('#timeframe'), box=$('[data-chart-timeframes]');
    if(select) select.innerHTML=tf.length?tf.map(x=>`<option value="${safe(x.seconds)}">${safe(x.label)}</option>`).join(''):'<option value="">Broker timeframes unavailable</option>';
    if(box){const active=select?.value||String(tf[0]?.seconds||'');box.innerHTML=tf.map(x=>`<button type="button" data-broker-timeframe="${safe(x.seconds)}" class="${String(x.seconds)===active?'active':''}">${safe(x.label)}</button>`).join('');box.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{box.querySelectorAll('button').forEach(x=>x.classList.remove('active'));b.classList.add('active');if(select)select.value=b.dataset.brokerTimeframe;if(mode==='candles')loadHistory();}));}
  }
  async function loadCaps(){
    if(!accountReady()) return;
    try{renderCaps(await api('/api/market/chart/capabilities/',{},9000));}
    catch(e){renderCaps({timeframes:[{seconds:60,label:'1m'},{seconds:300,label:'5m'},{seconds:900,label:'15m'},{seconds:3600,label:'1h'}]});}
  }
  async function loadHistory(){
    if(!symbol || !accountReady()) return;
    try{
      const tf=$('#timeframe')?.value||'';
      const url=mode==='candles'?`/api/market/chart/history/?symbol=${encodeURIComponent(symbol)}&mode=candles&granularity=${encodeURIComponent(tf)}&limit=120`:`/api/market/chart/history/?symbol=${encodeURIComponent(symbol)}&mode=ticks&limit=120`;
      const data=await api(url,{},10000);
      if(mode==='candles') candles=list(data.items).map(c=>({epoch:+c.epoch,open:+c.open,high:+c.high,low:+c.low,close:+c.close})).filter(c=>[c.open,c.high,c.low,c.close].every(Number.isFinite)).reverse(),points=[],renderCandles();
      else points=list(data.items).map(t=>({price:+(t.quote??t.price),epoch:+t.epoch})).filter(p=>Number.isFinite(p.price)).reverse().slice(-120),candles=[],renderTicks();
    }catch(e){$('[data-chart-loading]')?.replaceChildren(document.createTextNode(`Chart history unavailable: ${e.message||'request failed'}`));}
  }
  function close(){if(ws){try{ws.close()}catch(_){}ws=null;}clearTimeout(reconnect);}
  function connect(next){if(!next||document.visibilityState!=='visible'||!accountReady())return;symbol=next;closed=false;close();try{ws=new WebSocket(wsUrl());ws.addEventListener('open',()=>ws?.send(JSON.stringify({action:'subscribe',symbol})));ws.addEventListener('message',e=>{try{const p=JSON.parse(e.data);if(p.type!=='market.tick'||String(p.symbol||symbol)!==symbol)return;const price=Number(p.price);if(!Number.isFinite(price))return;$('[data-q="bid"]')?.replaceChildren(document.createTextNode(money(p.bid??price)));$('[data-q="ask"]')?.replaceChildren(document.createTextNode(money(p.ask??price)));if(mode==='ticks'){points.push({price,epoch:+p.epoch||Date.now()/1000});points=points.slice(-120);renderTicks();}else loadHistory();}catch(_){}});ws.addEventListener('close',()=>{ws=null;if(!closed&&document.visibilityState==='visible'&&accountReady())reconnect=setTimeout(()=>connect(symbol),3000);});ws.addEventListener('error',()=>{$('[data-chart-loading]')?.replaceChildren(document.createTextNode('Broker market stream reconnecting…'));});}catch(_){reconnect=setTimeout(()=>connect(symbol),3000);}}
  function setMode(m){mode=m;document.querySelectorAll('[data-chart-mode]').forEach(b=>b.classList.toggle('active',b.dataset.chartMode===m));const box=$('[data-chart-timeframes]');if(box)box.style.display=m==='candles'?'':'none';loadHistory();}
  function bind(){const s=$('#symbol');if(!s||s.dataset.chartBound==='1')return;s.dataset.chartBound='1';s.addEventListener('change',()=>{symbol=s.value;points=[];candles=[];close();if(symbol){loadHistory();connect(symbol);}});$('#timeframe')?.addEventListener('change',()=>mode==='candles'&&loadHistory());document.querySelectorAll('[data-chart-mode]').forEach(b=>b.addEventListener('click',()=>setMode(b.dataset.chartMode)));document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&s.value&&accountReady()){loadHistory();connect(s.value)}else if(document.visibilityState!=='visible'){closed=true;close()}});}
  async function start(){if(document.body.dataset.authenticated!=='true'||!$('#chart'))return;bind();let attempts=0;const wait=async()=>{const s=$('#symbol');if(s?.value){symbol=s.value;await loadCaps();await loadHistory();connect(symbol);return;}if(++attempts<40)setTimeout(wait,250);else $('[data-chart-loading]')?.replaceChildren(document.createTextNode('No broker market instrument available'));};wait();window.AlgoBotBrokerState?.subscribe(()=>{const s=$('#symbol');if(s?.value){loadCaps();loadHistory();connect(s.value)}});window.addEventListener('algobot:backend-accounts-loaded',()=>{const s=$('#symbol');if(s?.value){loadCaps();loadHistory();connect(s.value)}});}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
