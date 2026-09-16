/* Chart-first live market watchdog.
 * The pro chart remains the primary stream. This watchdog is deliberately
 * dormant while quote DOM updates are healthy and only opens a broker stream
 * after a short stale window, preventing a second permanent feed.
 */
(() => {
  'use strict';
  if (window.__algoBotTerminalMarketWatchdog) return;
  window.__algoBotTerminalMarketWatchdog = true;

  const $ = s => document.querySelector(s);
  const WS = 'wss://api.derivws.com/trading/v1/options/ws/public';
  let lastQuoteMutation = Date.now();
  let lastSymbol = '';
  let ws = null;
  let fallbackTimer = null;
  let active = false;

  const fmt = value => Number.isFinite(Number(value)) ? Number(value).toLocaleString(undefined, {maximumFractionDigits:8}) : 'Unavailable';
  const touch = () => { lastQuoteMutation = Date.now(); };
  const updateQuote = value => {
    if (!Number.isFinite(Number(value))) return;
    const text = fmt(value);
    $('[data-q="bid"]')?.replaceChildren(document.createTextNode(text));
    $('[data-q="ask"]')?.replaceChildren(document.createTextNode(text));
    touch();
    window.dispatchEvent(new CustomEvent('algobot:market-watchdog-tick', {detail:{symbol:lastSymbol,quote:Number(value),epoch:Math.floor(Date.now()/1000)}}));
    window.dispatchEvent(new CustomEvent('algobot:market-data-state', {detail:{state:'live',detail:'live broker quote · chart watchdog'}}));
  };
  const close = () => { active=false;try{ws?.close()}catch(_){}ws=null;clearTimeout(fallbackTimer);fallbackTimer=null; };
  const connect = symbol => {
    if (!symbol || document.visibilityState !== 'visible' || active) return;
    active=true;lastSymbol=symbol;
    try { ws?.close(); } catch (_) {}
    ws=new WebSocket(WS);
    ws.onopen=()=>{try{ws.send(JSON.stringify({ticks:symbol,subscribe:1,req_id:Date.now()}))}catch(_){} };
    ws.onmessage=e=>{try{const d=JSON.parse(e.data);if(d.msg_type==='tick'&&!d.error&&d.tick?.quote!=null)updateQuote(d.tick.quote)}catch(_) {}};
    ws.onerror=()=>{};
    ws.onclose=()=>{ws=null;active=false;};
  };


  function boot(){
    if(!$('.terminal-page'))return;
    const bid=$('[data-q="bid"]'),ask=$('[data-q="ask"]');
    const observer=new MutationObserver(touch);
    if(bid)observer.observe(bid,{childList:true,characterData:true,subtree:true});
    if(ask)observer.observe(ask,{childList:true,characterData:true,subtree:true});
    $('#symbol')?.addEventListener('change',()=>{close();lastSymbol='';lastQuoteMutation=Date.now()});
    window.addEventListener('algobot:account-changed',()=>{close();lastQuoteMutation=Date.now()});
    window.addEventListener('algobot:account-synced',()=>{close();lastQuoteMutation=Date.now()});
    window.addEventListener('pagehide',()=>{close();observer.disconnect()},{once:true});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
