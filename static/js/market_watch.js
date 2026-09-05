/* Connected-broker market scanner. Preserves the existing catalogue and quote stream while adding professional discovery controls. */
(() => {
  'use strict';
  if (window.__algoBotMarketWatch) return;
  window.__algoBotMarketWatch = true;
  const $ = s => document.querySelector(s);
  const list = v => window.AlgoBotFrontendData?.list(v) || [];
  const esc = v => String(v ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[c]));
  const money = v => Number.isFinite(Number(v)) ? Number(v).toLocaleString(undefined,{maximumFractionDigits:8}) : 'Unavailable';
  const WS = 'wss://api.derivws.com/trading/v1/options/ws/public';
  const storedFavourites = () => {
    try {
      const value = JSON.parse(localStorage.getItem('algobot.market.favourites') || '[]');
      return Array.isArray(value) ? value.filter(Boolean).map(String) : [];
    } catch (_) {
      return [];
    }
  };
  let rows=[], quotes=new Map(), selectedMarket='All', selectedSort='name', favourites=new Set(storedFavourites()), selectedTimeframe='60', socket=null, reconnect=null, req=3000;
  const palette = market => { const k=String(market||'').toLowerCase(); if(k.includes('crypto')) return ['#f6a623','#bb5b12']; if(k.includes('forex')) return ['#3c91e6','#2553a4']; if(k.includes('commodity')) return ['#d69e2e','#8b5b15']; if(k.includes('stock')) return ['#8b5cf6','#5b21b6']; return ['#ff5a64','#b5203a']; };
  const initials = r => String(r.display_name||r.symbol||'?').split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase();
  function persist(){try{localStorage.setItem('algobot.market.favourites',JSON.stringify([...favourites]));}catch(_){}}
  function categories(){ const root=$('[data-market-categories]'); if(!root)return; const cats=['All',...new Set(rows.map(r=>r.market).filter(Boolean).sort())]; root.innerHTML=cats.map(c=>`<button type="button" class="${c===selectedMarket?'active':''}" data-market-category="${esc(c)}">${esc(c)}</button>`).join(''); root.querySelectorAll('[data-market-category]').forEach(b=>b.addEventListener('click',()=>{selectedMarket=b.dataset.marketCategory;categories();render();connect();})); }
  function filtered(){ const q=String($('[data-market-search]')?.value||'').trim().toLowerCase(); let a=rows.filter(r=>(selectedMarket==='All'||r.market===selectedMarket)&&(!q||JSON.stringify(r).toLowerCase().includes(q))); if(selectedSort==='favourite') a.sort((x,y)=>Number(favourites.has(y.symbol))-Number(favourites.has(x.symbol))); else if(selectedSort==='price') a.sort((x,y)=>(quotes.get(y.symbol)?.price??-Infinity)-(quotes.get(x.symbol)?.price??-Infinity)); else a.sort((x,y)=>String(x.display_name||x.symbol).localeCompare(String(y.display_name||y.symbol))); return a.slice(0,120); }
  function render(message=null){ const root=$('[data-market-list]'); if(!root)return; if(message){root.innerHTML=`<div class="market-empty">${esc(message)}</div>`;summary();return;} const items=filtered(); root.innerHTML=items.map(r=>{const [a,b]=palette(r.market),q=quotes.get(r.symbol),href=`/trading/?symbol=${encodeURIComponent(r.symbol)}${selectedTimeframe?`&timeframe=${encodeURIComponent(selectedTimeframe)}`:''}`,fav=favourites.has(r.symbol); const status=r.is_tradable===false?'CLOSED':'READY'; return `<article class="market-card ${fav?'is-favourite':''}" data-symbol="${esc(r.symbol)}"><button class="icon-btn" type="button" data-favourite="${esc(r.symbol)}" aria-label="${fav?'Remove':'Add'} ${esc(r.symbol)} ${fav?'from':'to'} favourites">${fav?'★':'☆'}</button><span class="market-avatar" style="--avatar-a:${a};--avatar-b:${b}" aria-hidden="true">${esc(initials(r))}</span><div class="market-card-copy"><span class="eyebrow">${esc(r.market||'Broker market')}</span><h2>${esc(r.symbol)}</h2><p>${esc(r.display_name||r.symbol)}</p></div><div class="market-quote"><strong data-quote>${q?money(q.price):'Waiting…'}</strong><span data-bidask>${q?`Bid ${money(q.bid)} · Ask ${money(q.ask)} · ${q.live?'LIVE':'STALE'}`:`${status} · Waiting for live broker quote`}</span></div><div class="market-card-actions"><a class="btn primary small" href="${href}">Trade</a></div></article>`;}).join('')||'<div class="market-empty">No broker instruments match your filters.</div>'; root.querySelectorAll('[data-favourite]').forEach(b=>b.addEventListener('click',()=>{const s=b.dataset.favourite;if(favourites.has(s))favourites.delete(s);else favourites.add(s);persist();render();connect();})); summary(); }
  function summary(){ const s=$('[data-scanner-total]'),f=$('[data-scanner-favourites]'),l=$('[data-scanner-live]'),m=$('[data-scanner-markets]'); if(s)s.textContent=filtered().length; if(f)f.textContent=rows.filter(r=>favourites.has(r.symbol)).length; if(l)l.textContent=[...quotes.values()].filter(q=>q.live).length; if(m)m.textContent=new Set(rows.map(r=>r.market).filter(Boolean)).size; }
  function update(payload){const t=payload.tick||{},symbol=String(t.symbol||payload.echo_req?.ticks||''),price=Number(t.quote);if(!symbol||!Number.isFinite(price))return;quotes.set(symbol,{price,bid:Number(t.bid??price),ask:Number(t.ask??price),live:true});const card=document.querySelector(`[data-symbol="${CSS.escape(symbol)}"]`);if(card){card.querySelector('[data-quote]')?.replaceChildren(document.createTextNode(money(price)));card.querySelector('[data-bidask]')?.replaceChildren(document.createTextNode(`Bid ${money(t.bid??price)} · Ask ${money(t.ask??price)} · LIVE`));}summary();}
  function close(){if(socket){try{socket.close();}catch(_){ }socket=null;}clearTimeout(reconnect);}
  function connect(){const cards=[...document.querySelectorAll('[data-symbol]')].slice(0,12);if(!cards.length||document.visibilityState!=='visible')return;close();try{socket=new WebSocket(WS);socket.addEventListener('open',()=>cards.forEach(c=>socket?.send(JSON.stringify({ticks:c.dataset.symbol,subscribe:1,req_id:++req}))));socket.addEventListener('message',e=>{try{const p=JSON.parse(e.data);if(!p.error&&p.msg_type==='tick')update(p);}catch(_){}});socket.addEventListener('close',()=>{socket=null;if(document.visibilityState==='visible')reconnect=setTimeout(connect,2500);});}catch(_){reconnect=setTimeout(connect,2500);}}
  async function loadSymbols(){
    const endpoint='/api/market/broker-catalogue/';
    let apiError=null;
    try{
      const data=await window.AlgoBotFrontendData.request(endpoint,{},10000);
      rows=list(data?.symbols??data).filter(r=>r?.is_active!==false);
      if(!rows.length)throw new Error('Connected broker returned no active instruments');
    }catch(e){
      apiError=e;
      try{
        if(typeof window.AlgoBotPublicMarketData?.catalogue==='function') rows=await window.AlgoBotPublicMarketData.catalogue(7000);
        if(!rows.length)throw new Error('Public broker returned no active instruments');
      }catch(publicError){
        throw new Error(`Broker catalogue unavailable (${apiError?.message||'API failed'}; public fallback: ${publicError?.message||'failed'})`);
      }
    }
    categories();render();connect();return rows;
  }
  function timeframes(){const s=$('[data-market-timeframe]');if(!s)return;const frames=[[60,'1 minute'],[120,'2 minutes'],[300,'5 minutes'],[600,'10 minutes'],[900,'15 minutes'],[1800,'30 minutes'],[3600,'1 hour'],[7200,'2 hours'],[14400,'4 hours'],[28800,'8 hours'],[86400,'1 day']];s.innerHTML=frames.map(x=>`<option value="${x[0]}">${x[1]}</option>`).join('');selectedTimeframe=s.value||'60';}
  async function load(){render('Loading connected broker market catalogue…');try{timeframes();await loadSymbols();}catch(e){render(e.message||'Broker market catalogue unavailable.');}}
  function boot(){const search=$('[data-market-search]'),sort=$('[data-market-sort]');search?.addEventListener('input',()=>{render();connect();});sort?.addEventListener('change',e=>{selectedSort=e.target.value;render();connect();});$('[data-market-timeframe]')?.addEventListener('change',e=>{selectedTimeframe=e.target.value;render();});$('[data-market-refresh]')?.addEventListener('click',async e=>{e.currentTarget.disabled=true;try{await loadSymbols();}catch(err){if(rows.length)render();else render(err.message||'Broker catalogue refresh unavailable.');}finally{e.currentTarget.disabled=false;}});document.addEventListener('visibilitychange',()=>document.visibilityState==='visible'?connect():close());window.addEventListener('beforeunload',close,{once:true});load();}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
