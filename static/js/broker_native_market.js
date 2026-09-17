/* Live connected-broker market capability bridge.
 * Transport, timeout, account context and error reporting are centralized in
 * AlgoBotServices. This module only renders broker-specific capabilities.
 */
(() => {
  'use strict';
  if (window.__algoBotBrokerNativeMarket) return;
  window.__algoBotBrokerNativeMarket = true;

  const $=(s,r=document)=>r.querySelector(s);
  const esc=v=>String(v??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[c]));
  const list=v=>window.AlgoBotFrontendData?.list?.(v)||[];
  const api=(url,options={},timeout=12000)=>window.AlgoBotServices?.request?.('market-data',url,options,timeout)||window.AlgoBotFrontendData?.request?.(url,options,timeout);
  let contracts=[],capabilitiesRequest=0,capabilitiesInFlight=null,capabilitiesSymbol='';
  const capabilitiesCacheKey=symbol=>'algobot:broker-capabilities:v2:'+String(window.AlgoBotAccountContext?.getSelectedId?.()||window.AlgoBotBrokerState?.get?.()?.account?.id||'none')+':'+symbol;
  const readCapabilitiesCache=symbol=>{try{const item=JSON.parse(sessionStorage.getItem(capabilitiesCacheKey(symbol))||'null');return item?.payload||null}catch(_){return null}};
  const writeCapabilitiesCache=(symbol,payload)=>{try{sessionStorage.setItem(capabilitiesCacheKey(symbol),JSON.stringify({at:Date.now(),payload}))}catch(_){} };

  const directionFor=type=>/PUT|FALL|LOWER|MULTDOWN|DIGITUNDER|NOTOUCH|TURBOSSHORT|RUNLOW|EXPIRYMISS/i.test(String(type||''))?'SELL':'BUY';
  const setStatus=message=>$('[data-contract-status]')?.replaceChildren(document.createTextNode(String(message||'')));
  const setPreparedDirection=direction=>{const normalized=String(direction||'').toUpperCase();if(!['BUY','SELL'].includes(normalized))return;[$('[data-direct-buy]'),$('[data-direct-sell]')].filter(Boolean).forEach(button=>{const buttonDirection=String(button.dataset.direction||'').toUpperCase();const active=buttonDirection===normalized;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));button.disabled=!active});window.__algobotPreparedManualDirection=normalized;window.dispatchEvent(new CustomEvent('algobot:broker-direction-prepared',{detail:{direction:normalized}}))};
  function disableDirections(disabled=true){[$('[data-direct-buy]'),$('[data-direct-sell]')].filter(Boolean).forEach(button=>{button.disabled=disabled;if(disabled){button.classList.remove('active');button.setAttribute('aria-pressed','false')}})}
  function renderContracts(payload){
    const root=payload?.contracts_for||payload?.data?.contracts_for||payload;
    const raw=Array.isArray(payload)?payload:(payload?.contracts||payload?.available||root?.available||[]);
    contracts=raw.filter(c=>c&&c.contract_type).map(c=>({...c,contract_type:String(c.contract_type),contract_category:String(c.contract_category||''),expiry_type:String(c.expiry_type||''),underlying_symbol:String(c.underlying_symbol||$('#symbol')?.value||'')}));
    const select=$('[data-contract-type]'),typeLabel=$('[data-broker-trade-type]');if(!select)return;
    if(!contracts.length){select.innerHTML='<option value="">No broker contracts available</option>';select.disabled=true;if(typeLabel)typeLabel.textContent='Unavailable';disableDirections(true);setStatus('Deriv reports no contracts for this instrument');return}
    const previous=select.value;select.innerHTML=contracts.map(c=>`<option value="${esc(c.contract_type)}">${esc(c.contract_type+(c.contract_category?` · ${c.contract_category}`:''))}</option>`).join('');select.disabled=false;select.value=contracts.some(c=>c.contract_type===previous)?previous:contracts[0].contract_type;applyContract(select.value);setStatus(`${contracts.length} broker-supported contract type${contracts.length===1?'':'s'}`);
  }
  function applyContract(type){const selected=contracts.find(c=>String(c.contract_type)===String(type));if(!selected)return;setPreparedDirection(directionFor(selected.contract_type));const label=$('[data-broker-trade-type]');if(label)label.textContent=selected.contract_category||selected.contract_type||'Broker contract';window.__algobotSelectedBrokerContract=selected;window.__algobotAiOrderContext={...(window.__algobotAiOrderContext||{}),broker_source:'connected_broker',contract_type:selected.contract_type,contract_category:selected.contract_category||'',expiry_type:selected.expiry_type||'',underlying_symbol:selected.underlying_symbol||$('#symbol')?.value||'',sentiment:selected.sentiment||'',market:selected.market||'',submarket:selected.submarket||''};window.dispatchEvent(new CustomEvent('algobot:broker-contract-selected',{detail:selected}))}
  async function loadCapabilities(symbol, retryAttempt=0){
     const normalized=String(symbol||'').trim();
     const select=$('[data-contract-type]');
     if(!select||!normalized)return;
     if(capabilitiesInFlight && capabilitiesSymbol===normalized){
       try{return await capabilitiesInFlight}catch(_){return}
     }
     const requestId=++capabilitiesRequest;
     if(capabilitiesInFlight && capabilitiesSymbol!==normalized)capabilitiesInFlight=null;
     capabilitiesSymbol=normalized;
     const cached=readCapabilitiesCache(normalized);
     if(cached){renderContracts(cached);setStatus('Broker contracts loaded from the last verified broker snapshot.');}
     else {select.disabled=true;select.innerHTML='<option value="">Loading broker contracts…</option>';if($('[data-broker-trade-type]'))$('[data-broker-trade-type]').textContent='Loading';disableDirections(true);setStatus('Loading broker-supported contracts…');}
     capabilitiesInFlight=(async()=>{
       try{
         const payload=await api(`/api/market/broker-capabilities/?symbol=${encodeURIComponent(normalized)}`,{notifyOnError:false},12000);
         if(requestId===capabilitiesRequest){writeCapabilitiesCache(normalized,payload);renderContracts(payload);}
         return payload;
       }catch(error){
         if(requestId!==capabilitiesRequest)return null;
         if(error?.code==='REQUEST_ABORTED'||/signal.*aborted|request.*aborted/i.test(error?.message||'')){setStatus('Broker capability request was cancelled. Use Refresh market to try again.');return null;}
         if(['NETWORK_ERROR','API_TIMEOUT','SERVICE_TIMEOUT'].includes(String(error?.code||''))){setStatus('Broker capability connection delayed. Use Refresh market to try again.');return null;}
         const cachedPayload=readCapabilitiesCache(normalized);
         if(cachedPayload){renderContracts(cachedPayload);setStatus('Using the last verified broker contract snapshot. Use Refresh market to revalidate.');return null;}
         contracts=[];select.innerHTML='<option value="">Broker contracts unavailable</option>';select.disabled=true;if($('[data-broker-trade-type]'))$('[data-broker-trade-type]').textContent='Unavailable';disableDirections(true);setStatus('Broker contracts are temporarily unavailable. Use Retry or refresh the broker connection.');return null;
       }finally{capabilitiesInFlight=null;}
     })();
     return await capabilitiesInFlight;
   }
  const currentSymbol=()=>String($('#symbol')?.value||'').trim();
  const triggerCurrentSymbol=()=>{const symbol=currentSymbol();if(symbol)void loadCapabilities(symbol)};
  function boot(){if(!$('.terminal-page'))return;const symbol=$('#symbol'),contract=$('[data-contract-type]');disableDirections(true);symbol?.addEventListener('change',()=>loadCapabilities(symbol.value));contract?.addEventListener('change',()=>applyContract(contract.value));window.addEventListener('algobot:broker-symbols-loaded',triggerCurrentSymbol);window.addEventListener('algobot:market-symbol-changed',triggerCurrentSymbol);window.addEventListener('algobot:account-changed',triggerCurrentSymbol);window.addEventListener('algobot:account-synced',triggerCurrentSymbol);window.addEventListener('pagehide',()=>{capabilitiesRequest++;capabilitiesInFlight=null},{once:true});if(currentSymbol())triggerCurrentSymbol()}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
