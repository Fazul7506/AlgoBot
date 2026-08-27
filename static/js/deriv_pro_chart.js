(() => {
  'use strict';
  if (window.__algoBotProChart) return;
  window.__algoBotProChart = true;

  const $ = s => document.querySelector(s);
  const L = () => window.LightweightCharts;
  const WS = 'wss://api.derivws.com/trading/v1/options/ws/public';
  const TF = [['1m',60],['2m',120],['5m',300],['10m',600],['15m',900],['30m',1800],['1h',3600],['2h',7200],['4h',14400],['8h',28800],['1d',86400]];
  const OVERLAYS = [['sma20','SMA 20'],['ema50','EMA 50'],['wma20','WMA 20'],['bb20','Bollinger 20'],['vwap','VWAP']];
  const OSC = [['none','Off'],['rsi','RSI 14'],['macd','MACD 12/26/9'],['stoch','Stochastic 14/3'],['atr','ATR 14'],['cci','CCI 20'],['williams','Williams %R 14']];
  const state = {chart:null,main:null,overlays:{},osc:[],symbol:'',tf:60,type:'ticks',points:[],candles:[],current:null,overlay:new Set(['sma20','ema50']),oscillator:'none',ws:null,reconnect:null,req:10,renderTimer:null};
  const accountsReady = () => !!(window.AlgoBotBrokerAccounts?.length || window.AlgoBotBrokerState?.get()?.account);
  const epoch = v => { const n=Number(v); return Number.isFinite(n)?(n>20000000000?Math.floor(n/1000):Math.floor(n)):null; };
  const fmt = v => Number.isFinite(Number(v)) ? Number(v).toLocaleString(undefined,{maximumFractionDigits:8}) : 'Unavailable';
  const text = (sel,v) => $(sel)?.replaceChildren(document.createTextNode(String(v)));
  const bars = () => state.type==='candles' ? state.candles : state.points.map(p=>({time:p.time,open:p.price,high:p.price,low:p.price,close:p.price,volume:1}));
  const vals = () => bars().map(x=>x.close);
  const times = () => bars().map(x=>x.time);
  const clean = a => a.filter(Boolean);
  const sma = (v,p) => {const t=times(),o=[];for(let i=p-1;i<v.length;i++)o.push({time:t[i],value:v.slice(i-p+1,i+1).reduce((a,b)=>a+b,0)/p});return o;};
  const ema = (v,p) => {if(v.length<p)return[];const t=times(),o=[];let e=v.slice(0,p).reduce((a,b)=>a+b,0)/p;o.push({time:t[p-1],value:e});const k=2/(p+1);for(let i=p;i<v.length;i++){e=(v[i]-e)*k+e;o.push({time:t[i],value:e});}return o;};
  const wma = (v,p) => {const t=times(),d=p*(p+1)/2,o=[];for(let i=p-1;i<v.length;i++){let s=0;for(let j=0;j<p;j++)s+=v[i-j]*(p-j);o.push({time:t[i],value:s/d});}return o;};
  const bb = (v,p=20,m=2) => {const t=times(),mid=[],up=[],lo=[];for(let i=p-1;i<v.length;i++){const w=v.slice(i-p+1,i+1),a=w.reduce((x,y)=>x+y,0)/p,sd=Math.sqrt(w.reduce((x,y)=>x+(y-a)**2,0)/p);mid.push({time:t[i],value:a});up.push({time:t[i],value:a+m*sd});lo.push({time:t[i],value:a-m*sd});}return{mid,up,lo};};
  const vwap = d => {let pv=0,vol=0;return d.map(b=>{const q=Number(b.volume)||1;pv+=((b.high+b.low+b.close)/3)*q;vol+=q;return{time:b.time,value:pv/vol};});};
  const rsi = (v,p=14) => {if(v.length<=p)return[];const t=times(),o=[];let g=0,l=0;for(let i=1;i<=p;i++){const d=v[i]-v[i-1];g+=Math.max(d,0);l+=Math.max(-d,0);}g/=p;l/=p;const calc=()=>l===0?100:100-100/(1+g/l);o.push({time:t[p],value:calc()});for(let i=p+1;i<v.length;i++){const d=v[i]-v[i-1];g=(g*(p-1)+Math.max(d,0))/p;l=(l*(p-1)+Math.max(-d,0))/p;o.push({time:t[i],value:calc()});}return o;};
  const macd = v => {const f=ema(v,12),s=ema(v,26),m=new Map(s.map(x=>[x.time,x.value])),line=[];f.forEach(x=>{if(m.has(x.time))line.push({time:x.time,value:x.value-m.get(x.time)});});const a=line.map(x=>x.value),sig=[],t=line.map(x=>x.time);if(a.length>=9){let e=a.slice(0,9).reduce((x,y)=>x+y,0)/9;sig.push({time:t[8],value:e});const k=0.2;for(let i=9;i<a.length;i++){e=(a[i]-e)*k+e;sig.push({time:t[i],value:e});}}return{line,signal:sig,hist:clean(line.map(x=>{const z=sig.find(y=>y.time===x.time);return z?{time:x.time,value:x.value-z.value}:null;}))};};
  const stochastic = d => {const k=[];for(let i=13;i<d.length;i++){const w=d.slice(i-13,i+1),hi=Math.max(...w.map(x=>x.high)),lo=Math.min(...w.map(x=>x.low));k.push({time:d[i].time,value:hi===lo?50:100*(d[i].close-lo)/(hi-lo)});}return{k,d:sma(k.map(x=>x.value),3).map((x,i)=>({time:k[i+2].time,value:x.value}))};};
  const atr = (d,p=14) => {const tr=d.map((b,i)=>i?Math.max(b.high-b.low,Math.abs(b.high-d[i-1].close),Math.abs(b.low-d[i-1].close)):b.high-b.low);return sma(tr,p);};
  const cci = (d,p=20) => {const t=d.map(x=>(x.high+x.low+x.close)/3),o=[];for(let i=p-1;i<t.length;i++){const w=t.slice(i-p+1,i+1),m=w.reduce((a,b)=>a+b,0)/p,md=w.reduce((a,b)=>a+Math.abs(b-m),0)/p;o.push({time:d[i].time,value:md?((t[i]-m)/(0.015*md)):0});}return o;};
  const williams = (d,p=14) => {const o=[];for(let i=p-1;i<d.length;i++){const w=d.slice(i-p+1,i+1),hi=Math.max(...w.map(x=>x.high)),lo=Math.min(...w.map(x=>x.low));o.push({time:d[i].time,value:hi===lo?-50:-100*(hi-d[i].close)/(hi-lo)});}return o;};

  function normalizeTicks(h){const t=h?.times||[],p=h?.prices||[];return t.map((x,i)=>({time:epoch(x),price:Number(p[i])})).filter(x=>x.time&&Number.isFinite(x.price)).slice(-500);}
  function normalizeCandles(c){return (c||[]).map(x=>({time:epoch(x.epoch??x.time),open:Number(x.open),high:Number(x.high),low:Number(x.low),close:Number(x.close),volume:Number(x.tick_count)||1})).filter(x=>x.time&&[x.open,x.high,x.low,x.close].every(Number.isFinite)).slice(-500);}

  function request(payload,timeout=12000){return new Promise((resolve,reject)=>{let ws,timer;const id=++state.req;const done=(err,data)=>{clearTimeout(timer);try{ws?.close();}catch(_){}err?reject(err):resolve(data);};try{ws=new WebSocket(WS);}catch(e){reject(e);return;}timer=setTimeout(()=>done(new Error('Deriv market-data request timed out')),timeout);ws.onopen=()=>ws.send(JSON.stringify({...payload,req_id:id}));ws.onmessage=e=>{try{const d=JSON.parse(e.data);if(d.error)return done(new Error(d.error.message||'Deriv request rejected'));if(Number(d.req_id)===id)done(null,d);}catch(err){done(err);}};ws.onerror=()=>done(new Error('Deriv public market-data connection failed'));});}
  async function history(){
    if(!state.symbol||!accountsReady())return;
    text('[data-chart-loading]',`Loading ${state.symbol} directly from Deriv…`);
    try{
      if(state.type==='candles'){const d=await request({ticks_history:state.symbol,end:'latest',count:500,style:'candles',granularity:state.tf});state.candles=normalizeCandles(d.candles);state.points=[];state.current=state.candles.at(-1)||null;}
      else{const d=await request({ticks_history:state.symbol,end:'latest',count:500,style:'ticks'});state.points=normalizeTicks(d.history);state.candles=[];state.current=null;}
      draw(true);connect();
    }catch(e){
      try{const q=new URLSearchParams({symbol:state.symbol,mode:state.type,limit:'500',granularity:String(state.tf)});const d=await window.AlgoBotFrontendData.request(`/api/market/chart/history/?${q}`,{},12000);if(state.type==='candles'){state.candles=normalizeCandles(d.items);state.points=[];}else{state.points=(d.items||[]).map(x=>({time:epoch(x.epoch??x.time),price:Number(x.quote??x.price)})).filter(x=>x.time&&Number.isFinite(x.price)).slice(-500);}draw(true);connect();}catch(f){text('[data-chart-loading]',`Live broker chart unavailable: ${f.message||e.message}`);}
    }
  }

  function makeChart(){
    const c=$('#chart');if(!c||!L()?.createChart)return false;if(state.chart)state.chart.remove();c.innerHTML='';
    const x=L();state.chart=x.createChart(c,{autoSize:true,layout:{background:{type:'solid',color:'transparent'},textColor:'#a7b0bd',panes:{enableResize:true}},grid:{vertLines:{color:'rgba(148,163,184,.08)'},horzLines:{color:'rgba(148,163,184,.08)'}},crosshair:{mode:x.CrosshairMode?.Normal??0},rightPriceScale:{borderColor:'rgba(148,163,184,.16)'},timeScale:{borderColor:'rgba(148,163,184,.16)',timeVisible:true,secondsVisible:false,rightOffset:5},handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:true},handleScale:{axisPressedMouseMove:true,mouseWheel:true,pinch:true}});
    state.chart.subscribeCrosshairMove(p=>{const b=p?.seriesData?.get(state.main);if(!b)return;const close=Number(b.close??b.value);text('[data-chart-ohlc]',`O ${fmt(b.open??close)} · H ${fmt(b.high??close)} · L ${fmt(b.low??close)} · C ${fmt(close)}`);});return true;
  }
  function series(data,opt,pane=0){const s=state.chart.addSeries(L().LineSeries,{lineWidth:2,priceLineVisible:false,lastValueVisible:false,...opt},pane);s.setData(data);return s;}
  function clearIndicators(){Object.values(state.overlays).forEach(s=>{try{state.chart.removeSeries(s);}catch(_){}});state.overlays={};state.osc.forEach(s=>{try{state.chart.removeSeries(s);}catch(_){}});state.osc=[];if(state.chart?.panes?.().length>1)try{state.chart.removePane(1);}catch(_){} }
  function indicators(){
    clearIndicators();const d=bars(),v=d.map(x=>x.close);if(v.length<2)return;
    if(state.overlay.has('sma20'))state.overlays.sma20=series(sma(v,20),{color:'#f59e0b'});
    if(state.overlay.has('ema50'))state.overlays.ema50=series(ema(v,50),{color:'#60a5fa'});
    if(state.overlay.has('wma20'))state.overlays.wma20=series(wma(v,20),{color:'#a78bfa'});
    if(state.overlay.has('bb20')){const b=bb(v);state.overlays.bbMid=series(b.mid,{color:'#94a3b8',lineWidth:1});state.overlays.bbUp=series(b.up,{color:'#22c55e',lineWidth:1});state.overlays.bbLo=series(b.lo,{color:'#ef4444',lineWidth:1});}
    if(state.overlay.has('vwap'))state.overlays.vwap=series(vwap(d),{color:'#f97316'});
    if(state.oscillator==='none')return;
    const o=state.oscillator;if(o==='rsi')state.osc=[series(rsi(v),{color:'#22c55e'},1)];
    if(o==='macd'){const m=macd(v);state.osc=[series(m.line,{color:'#60a5fa'},1),series(m.signal,{color:'#f59e0b'},1),series(m.hist,{color:'#94a3b8',lineWidth:1},1)];}
    if(o==='stoch'){const z=stochastic(d);state.osc=[series(z.k,{color:'#60a5fa'},1),series(z.d,{color:'#f59e0b'},1)];}
    if(o==='atr')state.osc=[series(atr(d),{color:'#a78bfa'},1)];
    if(o==='cci')state.osc=[series(cci(d),{color:'#22c55e'},1)];
    if(o==='williams')state.osc=[series(williams(d),{color:'#f97316'},1)];
    const panes=state.chart.panes();if(panes[1])panes[1].setHeight(150);
  }
  function draw(fit){
    if(!state.chart)return;const x=L();if(state.main)try{state.chart.removeSeries(state.main);}catch(_){}state.main=state.type==='candles'?state.chart.addSeries(x.CandlestickSeries,{upColor:'#22c55e',downColor:'#ef4444',borderUpColor:'#22c55e',borderDownColor:'#ef4444',wickUpColor:'#22c55e',wickDownColor:'#ef4444'}):state.chart.addSeries(x.LineSeries,{color:'#60a5fa',lineWidth:2,priceLineVisible:false});state.main.setData(state.type==='candles'?state.candles:state.points.map(p=>({time:p.time,value:p.price})));indicators();const v=vals();if(v.length){const first=v[0],last=v.at(-1),mean=v.reduce((a,b)=>a+b,0)/v.length,vol=Math.sqrt(v.reduce((a,b)=>a+(b-mean)**2,0)/v.length);text('[data-trend]',last>=first?'Bullish':'Bearish');text('[data-volatility]',fmt(vol));text('[data-structure]',state.type==='candles'?'Deriv broker candles':'Deriv broker ticks');text('[data-chart-loading]',`Live Deriv data · ${v.length} ${state.type==='candles'?'candles':'ticks'}`);}if(fit)state.chart.timeScale().fitContent();}
  function livePrice(p){if(!state.main||!Number.isFinite(p))return;const last=state.type==='candles'?state.candles.at(-1)?.close:state.points.at(-1)?.price;text('[data-q="bid"]',fmt(p));text('[data-q="ask"]',fmt(p));if(last!=null&&Math.abs(p-last)>0){try{state.main.update(state.type==='candles'?state.candles.at(-1):{time:Math.floor(Date.now()/1000),value:p});}catch(_){} } }
  function onTick(t){const p=Number(t.quote),e=epoch(t.epoch)||Math.floor(Date.now()/1000);if(!Number.isFinite(p))return;if(state.type==='candles'){const bucket=Math.floor(e/state.tf)*state.tf;if(!state.current||state.current.time!==bucket){state.current={time:bucket,open:p,high:p,low:p,close:p,volume:1};state.candles.push(state.current);state.candles=state.candles.slice(-500);}else{state.current.high=Math.max(state.current.high,p);state.current.low=Math.min(state.current.low,p);state.current.close=p;}state.main?.update(state.current);}else{state.points.push({time:e,price:p});state.points=state.points.slice(-500);state.main?.update({time:e,value:p});}livePrice(p);clearTimeout(state.renderTimer);state.renderTimer=setTimeout(()=>{indicators();},300);}
  function connect(){if(!state.symbol||!accountsReady()||document.visibilityState!=='visible')return;try{state.ws?.close();}catch(_){}state.ws=new WebSocket(WS);state.ws.onopen=()=>{state.ws.send(JSON.stringify({ticks:state.symbol,subscribe:1,req_id:++state.req}));text('[data-chart-loading]',`Connected directly to Deriv · ${state.symbol}`);};state.ws.onmessage=e=>{try{const d=JSON.parse(e.data);if(d.msg_type==='tick'&&!d.error)onTick(d.tick||{});}catch(_){}};state.ws.onclose=()=>{state.ws=null;if(document.visibilityState==='visible'){clearTimeout(state.reconnect);state.reconnect=setTimeout(connect,2500);}};state.ws.onerror=()=>text('[data-chart-loading]','Deriv market stream reconnecting…');}
  function controls(){
    const tfBox=$('[data-chart-timeframes]');if(tfBox){tfBox.innerHTML=TF.map(x=>`<button type="button" data-pro-tf="${x[1]}" class="${x[1]===state.tf?'active':''}">${x[0]}</button>`).join('');tfBox.querySelectorAll('button').forEach(b=>b.onclick=()=>{state.tf=Number(b.dataset.proTf);tfBox.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===b));if(state.type==='candles')history();});}
    const old=$('.chart-indicators');if(old){old.innerHTML=`<div class="indicator-group"><span>Overlays</span>${OVERLAYS.map(x=>`<button type="button" data-pro-overlay="${x[0]}" class="${state.overlay.has(x[0])?'active':''}">${x[1]}</button>`).join('')}</div><div class="indicator-group"><label>Oscillator <select data-pro-osc>${OSC.map(x=>`<option value="${x[0]}">${x[1]}</option>`).join('')}</select></label></div>`;old.querySelectorAll('[data-pro-overlay]').forEach(b=>b.onclick=()=>{const k=b.dataset.proOverlay;if(state.overlay.has(k))state.overlay.delete(k);else state.overlay.add(k);b.classList.toggle('active',state.overlay.has(k));indicators();});old.querySelector('[data-pro-osc]').onchange=e=>{state.oscillator=e.target.value;indicators();};}
    document.querySelectorAll('[data-chart-mode]').forEach(b=>b.onclick=()=>{state.type=b.dataset.chartMode;b.classList.toggle('active',true);document.querySelectorAll('[data-chart-mode]').forEach(x=>{if(x!==b)x.classList.remove('active');});if(tfBox)tfBox.style.display=state.type==='candles'?'':'none';history();});
    document.querySelectorAll('[data-chart-action]').forEach(b=>b.onclick=()=>{const a=b.dataset.chartAction;if(a==='fit')state.chart?.timeScale().fitContent();if(a==='live')state.chart?.timeScale().scrollToRealTime();if(a==='fullscreen')document.querySelector('.terminal-chart-panel')?.requestFullscreen?.();if(a==='screenshot'){const c=state.chart?.takeScreenshot(true,true);if(c){const a=document.createElement('a');a.href=c.toDataURL('image/png');a.download=`algobot-${state.symbol}.png`;a.click();}}if(a==='export'){const r=bars();const h=state.type==='candles'?'time,open,high,low,close':'time,price';const body=r.map(x=>state.type==='candles'?[x.time,x.open,x.high,x.low,x.close].join(','):[x.time,x.close].join(',')).join('\n');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([h+'\n'+body],{type:'text/csv'}));a.download=`algobot-${state.symbol}.csv`;a.click();}});
  }
  function start(){if(!$('#chart'))return;controls();if(!makeChart())return;const s=$('#symbol');const wait=()=>{if(s?.value){state.symbol=s.value;history();}else setTimeout(wait,250);};wait();s?.addEventListener('change',()=>{state.symbol=s.value;history();});window.addEventListener('algobot:backend-accounts-loaded',()=>{if(s?.value){state.symbol=s.value;history();}});document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&state.symbol){history();connect();}else{try{state.ws?.close();}catch(_){}}});}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
