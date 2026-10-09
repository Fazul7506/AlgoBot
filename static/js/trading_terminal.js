/* Reliable broker-backed trading terminal. */
(() => {
  'use strict';
  if (window.__algoBotTradingTerminal) return;
  window.__algoBotTradingTerminal = true;
  const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
  const list=v=>window.AlgoBotFrontendData?.list(v)||[];
  const esc=v=>String(v??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[c]));
  const money=v=>v==null||v===''||!Number.isFinite(Number(v))?'Unavailable':Number(v).toLocaleString(undefined,{maximumFractionDigits:8});
  // All terminal API traffic goes through the shared service facade so account
  // headers, transport, timeout, retry and error lifecycle are identical to the
  // dashboard and every other authenticated workspace.
  const canonicalApi=(u,o={},t=10000)=>window.AlgoBotFrontendData.request(u,o,t);
  const api=(u,o={},t=10000)=>{const options={credentials:'include',...o};return window.AlgoBotServices?.request?.('trading',u,options,t)||canonicalApi(u,options,t)};
  // Account selection is owned by the canonical account context. Keep the
  // authoritative endpoint shape explicit here for UI-contract validation and
  // future diagnostics; no second account-selection implementation is created.
  const switchAuthoritativeAccount=id=>window.AlgoBotAccountContext.selectAccount(id);
  let accounts=[],symbols=[],direction='BUY',busy=false,activeAccountId=null,directExecutionBusy=false,executionUncertain=false,catalogueLoadSeq=0,recordsLoadSeq=0,signalsLoadSeq=0;
  const requestedParams=new URLSearchParams(location.search),requestedStrategy=requestedParams.get('strategy')||'',requestedDirection=String(requestedParams.get('direction')||'').toUpperCase(),requestedSignalId=requestedParams.get('signal_id')||'';
  const selectedAccount=()=>window.AlgoBotAccountContext?.getSelected?.()||accounts.find(a=>String(a.id)===String(activeAccountId))||window.AlgoBotBrokerState?.get?.()?.account||null;
  // Mirror the backend's BrokerAccount.is_connection_eligible contract. A saved
  // account alone is not proof of a live, authorized broker connection.
  const brokerReady=()=>{const a=selectedAccount();return !!a&&String(a.status||'').toLowerCase()==='active'&&String(a.broker?.status||'').toLowerCase()==='active'&&a.is_connected===true&&String(a.credential_status||'').toLowerCase()==='ready'};
  const brokerReadinessReason=()=>{const a=selectedAccount();if(!a)return 'Connect a broker first';if(String(a.status||'').toLowerCase()!=='active')return 'Broker account is inactive';if(String(a.broker?.status||'').toLowerCase()!=='active')return 'Broker is unavailable';if(a.is_connected!==true)return 'Broker connection is not verified';if(String(a.credential_status||'').toLowerCase()!=='ready')return 'Broker credentials need attention';return 'Pre-trade checks active'};
  const syncExecutionControls=() => { const prepared=String(window.__algobotPreparedManualDirection||'').toUpperCase(); $$('[data-direct-buy],[data-direct-sell]').forEach(b=>{const matches=prepared&&String(b.dataset.direction||'').toUpperCase()===prepared;b.disabled=directExecutionBusy||executionUncertain||!brokerReady()||!matches;b.setAttribute('aria-disabled',String(b.disabled));}); };
  const result=(m,s='info')=>{const n=$('[data-order-result]');if(n){n.hidden=false;n.dataset.state=s;n.textContent=m}};
  const previewResult=(m,s='info')=>{const n=$('[data-order-preview-result]');if(n){n.hidden=false;n.dataset.state=s;n.textContent=m}};
  const renderRows=(selector,rows,empty,format)=>{const n=$(selector);if(n)n.innerHTML=rows.length?rows.map(format).join(''):`<div class="empty-state">${esc(empty)}</div>`};
  function renderSelectedStrategy(){const h=$('[name="strategy"]'),b=$('[data-selected-strategy] strong'),v=requestedStrategy.trim();if(h)h.value=v;if(b)b.textContent=v||'Manual trading';if(requestedDirection==='BUY'||requestedDirection==='SELL'){direction=requestedDirection;const button=document.querySelector(`[data-direct-${requestedDirection.toLowerCase()}]`);button?.setAttribute('aria-label',`Submit ${requestedDirection} contract from broker signal ${requestedSignalId||'selected signal'}`)}}
  function renderAccount(a){const st=$('#terminal-status'),note=$('[data-terminal-account]'),risk=$('[data-risk-check]');if(!a){if(st)st.textContent='Broker account required';if(note)note.textContent='No connected account';if(risk)risk.textContent='Connect broker first';syncExecutionControls();return}const broker=a.broker?.name||a.broker_name||'Broker';if(st)st.textContent=brokerReady()?`${broker} connected`:`${broker} connection required`;if(note)note.textContent=`Account: ${a.broker_account_id||a.account_id||a.loginid||a.id}`;if(risk)risk.textContent=brokerReadinessReason();syncExecutionControls()}
  function renderAccounts(rows){accounts=list(rows).filter(a=>a?.id);const s=$('#account');const central=window.AlgoBotAccountContext?.getSelected?.();const current=central?.id||activeAccountId||accounts.find(a=>a.is_active)?.id||null;activeAccountId=current;if(!s)return;if(!accounts.length){activeAccountId=null;s.innerHTML='<option value="">No connected broker account</option>';renderAccount(null);return}s.innerHTML=accounts.map(a=>`<option value="${esc(a.id)}">${esc(a.broker?.name||a.broker_name||'Broker')} · ${esc(a.broker_account_id||a.account_id)} · ${esc(a.account_type&&a.account_type!=='unknown'?a.account_type.toUpperCase():'')} · ${esc(a.currency||'')}</option>`).join('');s.value=String(activeAccountId||'');renderAccount(selectedAccount())}
  async function loadAccounts(){
  try{
    if(window.AlgoBotAccountContext){
      await window.AlgoBotAccountContext.load();
      accounts=window.AlgoBotAccountContext.getAccounts();
      const a=window.AlgoBotAccountContext.getSelected()||window.AlgoBotBrokerState?.get?.()?.account||null;
      activeAccountId=a?.id??null;
      if(a&&!accounts.some(x=>String(x.id)===String(a.id)))accounts=[a,...accounts];
      renderAccounts(accounts);
      return a;
    }
    const rows=await api('/api/brokers/accounts/',{},9000);
    renderAccounts(rows);
    return selectedAccount();
  }catch(e){
    const recovered=window.AlgoBotAccountContext?.getSelected?.()||window.AlgoBotBrokerState?.get?.()?.account||null;
    if(recovered){
      activeAccountId=recovered.id;
      if(!accounts.some(x=>String(x.id)===String(recovered.id)))accounts=[recovered,...accounts];
      renderAccounts(accounts);
      return recovered;
    }
    renderAccounts([]);
    result('Broker account data is temporarily unavailable. Use Refresh market or reconnect the broker.','error');
    return null;
  }
}
  async function switchAccount(id){if(!id||String(id)===String(activeAccountId))return selectedAccount();const previous=activeAccountId;const s=$('#account');if(s)s.disabled=true;result('Switching broker account…','pending');try{const a=await switchAuthoritativeAccount(id);activeAccountId=a.id;accounts=window.AlgoBotAccountContext.getAccounts();if(s)s.value=String(a.id);renderAccount(a);result(`Active account: ${a.broker_account_id||a.account_id||a.id}`,'success');await Promise.all([loadSymbols(),loadQuote(),loadRecords(),loadSignals()]);return a}catch(e){activeAccountId=previous;if(s)s.value=previous?String(previous):'';renderAccount(selectedAccount());result(`Account switch rejected: ${e.message||'request failed'}`,'error');return null}finally{if(s)s.disabled=false}}
  function renderWatchlist(filter=''){const n=$('[data-watchlist]');if(!n)return;const q=String(filter).trim().toLowerCase(),rows=symbols.filter(r=>!q||String(r.symbol||'').toLowerCase().includes(q)||String(r.display_name||'').toLowerCase().includes(q)),cur=$('#symbol')?.value,c=$('[data-watchlist-count]');if(c)c.textContent=String(symbols.length);n.innerHTML=rows.length?rows.slice(0,100).map(r=>`<button type="button" class="watchlist-row ${r.symbol===cur?'active':''}" data-watch-symbol="${esc(r.symbol)}"><span><strong>${esc(r.display_name||r.symbol)}</strong></span><b>›</b></button>`).join(''):'<div class="empty-state">No matching instruments.</div>';n.querySelectorAll('[data-watch-symbol]').forEach(b=>b.addEventListener('click',()=>selectSymbol(b.dataset.watchSymbol)))}
  function selectSymbol(symbol){const s=$('#symbol');if(!s||!symbols.some(r=>r.symbol===symbol))return;s.value=symbol;s.dispatchEvent(new Event('change',{bubbles:true}));renderWatchlist($('[data-watchlist-search]')?.value||'')}
  const catalogueCacheKey=()=>`algobot:terminal-catalogue:v3:${window.AlgoBotAccountContext?.getSelectedId?.()||window.AlgoBotBrokerState?.get?.()?.account?.id||'none'}`;
  const readCatalogueCache=()=>{try{const v=JSON.parse(sessionStorage.getItem(catalogueCacheKey())||'null');return v&&Array.isArray(v.symbols)&&v.symbols.length?v:null}catch(_){return null}};
  const writeCatalogueCache=rows=>{try{sessionStorage.setItem(catalogueCacheKey(),JSON.stringify({at:Date.now(),symbols:rows}))}catch(_){}};
  const paintSymbols=(s,rows,previous)=>{symbols=rows.filter(r=>r?.symbol&&r.is_active!==false&&r.is_tradable!==false);if(!symbols.length)return'';s.innerHTML=symbols.map(r=>`<option value="${esc(r.symbol)}">${esc(r.display_name||r.symbol)}</option>`).join('');const requested=new URLSearchParams(location.search).get('symbol');s.value=[previous,requested,symbols[0].symbol].find(v=>symbols.some(r=>r.symbol===v))||symbols[0].symbol;renderWatchlist($('[data-watchlist-search]')?.value||'');window.dispatchEvent(new CustomEvent('algobot:broker-symbols-loaded',{detail:{count:symbols.length}}));return s.value};
  async function loadSymbols(){
     const s=$('#symbol');if(!s)return'';
     const seq=++catalogueLoadSeq;
     const accountId=String(window.AlgoBotAccountContext?.getSelectedId?.()||window.AlgoBotBrokerState?.get?.()?.account?.id||'none');
     const previous=s.value;
     const cached=readCatalogueCache();
     const isCurrent=()=>seq===catalogueLoadSeq&&accountId===String(window.AlgoBotAccountContext?.getSelectedId?.()||window.AlgoBotBrokerState?.get?.()?.account?.id||'none');
     if(cached?.symbols){
       const cachedValue=paintSymbols(s,cached.symbols,previous);
       if(cachedValue&&Date.now()-Number(cached.at||0)<300000){
         void api('/api/market/catalogue/',{notifyOnError:false},7000).then(p=>{
           if(!isCurrent())return;
           const rows=list(p?.symbols??p).filter(r=>r?.symbol&&r.is_active!==false&&r.is_tradable!==false);
           if(rows.length){if(p?.stale!==true&&String(p?.status||'').toLowerCase()!=='stale')writeCatalogueCache(rows);else result('Broker market catalogue is stale. Instrument availability will be rechecked before order preview.','warning');paintSymbols(s,rows,s.value)}
         }).catch(()=>{});
         return cachedValue;
       }
     }
     try{
       const p=await api('/api/market/catalogue/',{notifyOnError:false},7000);
       if(!isCurrent())return'';
       const rows=list(p?.symbols??p).filter(r=>r?.symbol&&r.is_active!==false&&r.is_tradable!==false);
       if(!rows.length)throw new Error('No active tradable broker instruments are available');
       if(p?.stale!==true&&String(p?.status||'').toLowerCase()!=='stale')writeCatalogueCache(rows);else result('Broker market catalogue is stale. Instrument availability will be rechecked before order preview.','warning');return paintSymbols(s,rows,previous);
     }catch(e){
       if(!isCurrent())return'';
       if(cached?.symbols){const value=paintSymbols(s,cached.symbols,previous);if(value){result('Live broker catalogue is unavailable; showing cached instruments. Contract availability and live quotes are rechecked before preview.','warning');return value}}
       return''
     }
   }
   async function loadQuote(){
    const symbol=$('#symbol')?.value;
    // Public market quotes do not require a connected trading account.
    if(!symbol)return;
    // The Deriv chart/watchdog owns the realtime quote. Avoid a competing HTTP
    // quote request that can fail while the live broker stream is healthy.
    const bid=$('[data-q="bid"]'),ask=$('[data-q="ask"]');
    const current=bid?.textContent?.trim();
    if(current && !/^(Unavailable|Waiting for broker quote…|Failed to fetch)$/i.test(current)){
      if(ask && (!ask.textContent||/^(Unavailable|Failed to fetch)$/i.test(ask.textContent.trim()))) ask.textContent=current;
    }
  }
  async function loadRecords(){
    const seq=++recordsLoadSeq,accountId=String(selectedAccount()?.id||'none');
    const current=()=>seq===recordsLoadSeq&&accountId===String(selectedAccount()?.id||'none');
    if(!brokerReady()){if(current()){renderRows('[data-positions]',[],'Connect a broker to load positions.',()=> '');renderRows('[data-orders]',[],'Connect a broker to load orders.',()=> '')}return}
    const [p,o]=await Promise.allSettled([api('/api/positions/open/',{},9000),api('/api/orders/?limit=8&account_scope=active',{},9000)]);
    if(!current())return;
    const pr=p.status==='fulfilled'?list(p.value):[],or=o.status==='fulfilled'?list(o.value).slice(0,8):[];
    const unresolved=or.some(order=>Boolean(order?.validation_context?.reconciliation_required)||['sent','submitted','pending','unknown'].includes(String(order?.status||'').toLowerCase()));
    if(unresolved){executionUncertain=true;result('A previous broker order is still unconfirmed. Terminal order buttons remain locked until broker state is reconciled. Do not retry.','error');syncExecutionControls();}
    else if(executionUncertain&&o.status==='fulfilled'){executionUncertain=false;result('The selected account order list is reconciled. Manual execution is available again.','success');syncExecutionControls();}
    renderRows('[data-positions]',pr,p.status==='rejected'?'Positions temporarily unavailable.':'No open positions.',r=>`<div class="mini-row"><strong>${esc(r.display_name||r.symbol||'—')}</strong><span>${esc(r.direction||r.side||'')}</span><b>${esc(r.profit??r.pnl??'—')}</b></div>`);
    renderRows('[data-orders]',or,o.status==='rejected'?'Orders temporarily unavailable.':'No orders yet.',r=>`<div class="mini-row"><strong>${esc(r.display_name||r.symbol||'—')}</strong><span>${esc(r.direction||r.side||'')}</span><b>${esc(r.status||'')}</b></div>`)
}
  async function loadSignals(){const n=$('[data-signals]');if(!n)return;const seq=++signalsLoadSeq,accountId=String(selectedAccount()?.id||'none'),current=()=>seq===signalsLoadSeq&&accountId===String(selectedAccount()?.id||'none');try{const rows=list(await api('/api/dashboard/signals/?limit=8',{},8000));if(!current())return;n.innerHTML=rows.length?rows.map(r=>`<div class="mini-row"><strong>${esc(r.display_name||r.symbol||'Signal')}</strong><span>${esc(r.direction||r.signal||r.action||'')}</span><b>${esc(r.confidence??r.status??'')}</b></div>`).join(''):'<div class="empty-state">No active strategy signals.</div>'}catch(_){if(current())n.innerHTML='<div class="empty-state">Signals temporarily unavailable.</div>'}}
  async function refresh(){if(busy)return;busy=true;try{renderSelectedStrategy();await loadAccounts();const [symbol]=await Promise.all([loadSymbols(),loadRecords(),loadSignals()]);await loadQuote();if(symbol)window.dispatchEvent(new CustomEvent('algobot:market-symbol-changed',{detail:{symbol}}))}finally{busy=false}}
  async function submitDirect(orderDirection){
    let previewPassed=false;
    try{
      const a=selectedAccount(),symbol=$('#symbol')?.value,contract=$('[data-contract-type]')?.value,stake=$('[name="stake"]')?.value||'1';
      const duration=Number($('[name="duration"]')?.value||60),durationUnit=String($('[name="duration_unit"]')?.value||'s').toLowerCase();
      if(!a?.id)throw new Error('No active broker account.');
      if(!brokerReady())throw new Error(brokerReadinessReason());
      if(!symbol||!contract)throw new Error('Broker instrument or contract is not ready.');
      if(!Number.isInteger(duration)||duration<1||!['s','t','m','h','d'].includes(durationUnit))throw new Error('Enter a valid positive duration and unit.');
      const requestId=`terminal-${orderDirection.toLowerCase()}-${crypto.randomUUID?.()||Date.now()}`;
      const payload={broker_account:a.id,symbol,contract_type:contract,direction:orderDirection.toLowerCase(),order_type:'market',stake,duration,duration_unit:durationUnit,strategy:'',client_request_id:requestId,routing_context:{broker_source:'connected_broker',contract_type:contract,underlying_symbol:symbol,selected_strategy:null,trigger:'manual-button',signal_id:null,authoritative_account_id:a.id,account_type:a.account_type||'',currency:a.currency||'',duration,duration_unit:durationUnit}};
      const contextFingerprint=JSON.stringify({accountId:String(a.id),symbol,contract,stake:String(stake),duration,durationUnit,direction:orderDirection});
      const preview=await api('/api/orders/preview/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({broker_account:a.id,symbol,contract_type:contract,direction:orderDirection.toLowerCase(),order_type:'market',stake,duration,duration_unit:durationUnit,strategy:'',validation_context:{broker_source:'connected_broker',contract_type:contract,underlying_symbol:symbol,authoritative_account_id:a.id,direction:orderDirection.toLowerCase()}})},20000);
      if(preview?.status!=='ready'){
        previewResult(`Pre-trade preview rejected. No order was submitted. ${preview?.detail||preview?.message||'Broker validation did not approve this order.'}`,'error');
        throw new Error(preview?.detail||preview?.message||'Authoritative pre-trade validation rejected this order.');
      }
      previewPassed=true;
      const estimate=preview.estimate||{},currency=estimate.currency||a.currency||'';
      previewResult(`PRE-TRADE ESTIMATE — NOT AN EXECUTED ORDER · ${contract} · ${symbol} · ${duration} ${({s:'seconds',t:'ticks',m:'minutes',h:'hours',d:'days'})[durationUnit]} · Stake ${stake} ${currency} · Proposal cost ${estimate.proposal_cost??'Unavailable'} · Estimated payout ${estimate.payout??'Unavailable'} · Potential profit ${estimate.potential_profit??'Unavailable'} · Quote age ${preview.market?.age_seconds??'unknown'}s.`,'success');
      const current=selectedAccount(),currentSymbol=$('#symbol')?.value,currentContract=$('[data-contract-type]')?.value,currentStake=$('[name="stake"]')?.value||'1',currentDuration=Number($('[name="duration"]')?.value||60),currentDurationUnit=String($('[name="duration_unit"]')?.value||'s').toLowerCase();
      if(JSON.stringify({accountId:String(current?.id||''),symbol:currentSymbol,contract:currentContract,stake:String(currentStake),duration:currentDuration,durationUnit:currentDurationUnit,direction:orderDirection})!==contextFingerprint){
        previewResult('Preview invalidated because the account or order configuration changed. No order was submitted.','error');
        throw new Error('Order context changed during pre-trade validation. No order was submitted.');
      }
      result(`Submitting ${orderDirection} after broker preview…`,'pending');
      const o=await api('/api/orders/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)},30000);
      const brokerReference=o.broker_reference||o.broker_order_id||o.contract_id,finalStatus=String(o.status||'').toLowerCase();
      if(['executed','filled'].includes(finalStatus))result(`Order ${orderDirection} executed by ${a.broker?.name||a.broker_name||'the selected broker'} · ${brokerReference||'broker confirmation received'}.`,'success');
      else if(['accepted','sent_to_broker','queued','validated'].includes(finalStatus))result(`Order ${orderDirection} is ${finalStatus.replaceAll('_',' ')}. Broker confirmation is still pending.`,'pending');
      else result(`Order ${orderDirection} returned status ${finalStatus||'unknown'}. Reconcile before retrying.`,'error');
      window.dispatchEvent(new CustomEvent('algobot:order-created',{detail:o}));
      await loadRecords();
    }catch(e){
      const uncertain=Number(e?.status)===503||Number(e?.status)===504||e?.code==='BROKER_EXECUTION_STATE_UNKNOWN';
      const detail=e?.message||'broker execution failed';
      if(!previewPassed&&!uncertain)previewResult(`Pre-trade preview failed; no order was submitted. ${detail}`,'error');
      if(uncertain){executionUncertain=true;syncExecutionControls();result(`Execution could not be confirmed. Do not retry. The selected account remains locked until broker state is reconciled. ${detail}`,'error');void loadRecords();}
      else result(`Order rejected: ${detail}`,'error');
    }finally{directExecutionBusy=false;syncExecutionControls();}
  }
  function executeDirect(d){if(directExecutionBusy)return;if(executionUncertain){result('A previous broker order remains unconfirmed. Reconcile before submitting another order.','error');return}const a=selectedAccount();if(!a?.id){result('No active broker account. Select a connected account first.','validation');void loadAccounts();return}if(!brokerReady()){result(`${brokerReadinessReason()}. No order was submitted.`,'validation');void loadAccounts();return}if(!$('#symbol')?.value||!$('[data-contract-type]')?.value){result('Broker instrument or contract is not ready.','validation');return}directExecutionBusy=true;syncExecutionControls();result(`Checking ${d} preview…`,'pending');void submitDirect(d)}
  function bindDirect(){$$('[data-direct-buy],[data-direct-sell]').forEach(b=>{if(b.dataset.recoveredDirect)return;b.dataset.recoveredDirect='1';b.addEventListener('click',e=>{e.preventDefault();e.stopImmediatePropagation();executeDirect(String(b.dataset.direction||'').toUpperCase())},true)})}
  function bindNavigation(){const links=$$('#app-sidebar nav a[href]');if(!links.length)return;const path=location.pathname.replace(/\/+$/,'')||'/';let best=null,score=-1;links.forEach(l=>{let h=l.getAttribute('href')||'';try{h=new URL(h,location.origin).pathname.replace(/\/+$/,'')||'/'}catch(_){return}const ok=h==='/'?path==='/' : path===h||path.startsWith(`${h}/`);if(ok&&h.length>score){best=l;score=h.length}l.classList.remove('active','is-current-page');l.removeAttribute('aria-current')});if(best){best.classList.add('active','is-current-page');best.setAttribute('aria-current','page')}}
  function boot(){if(!$('.terminal-page'))return;renderSelectedStrategy();bindDirect();bindNavigation();$('[data-order-form]')?.addEventListener('submit',e=>{e.preventDefault();e.stopImmediatePropagation()},true);$('[data-action="terminal-refresh"]')?.addEventListener('click',refresh);$('[data-watchlist-search]')?.addEventListener('input',e=>renderWatchlist(e.target.value));$('#symbol')?.addEventListener('change',()=>{loadQuote();renderWatchlist($('[data-watchlist-search]')?.value||'')});$('#account')?.addEventListener('change',e=>{void switchAccount(e.target.value)});window.addEventListener('algobot:account-changed',e=>{activeAccountId=e.detail?.id??activeAccountId;accounts=window.AlgoBotAccountContext?.getAccounts?.()||accounts;renderAccounts(accounts);loadQuote();loadRecords()});window.addEventListener('algobot:account-synced',e=>{activeAccountId=e.detail?.id??activeAccountId;accounts=window.AlgoBotAccountContext?.getAccounts?.()||accounts;renderAccounts(accounts);loadQuote();loadRecords()});window.addEventListener('algobot:broker-direction-prepared',syncExecutionControls);window.addEventListener('algobot:terminal-strategy-selected',()=>result('Trading profile changed. Manual BUY/SELL remains user-driven; no order was submitted.','info'));refresh()}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
