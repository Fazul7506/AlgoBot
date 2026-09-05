/* Live connected-broker market capability bridge.
 * Transport, timeout, account context and error reporting are centralized in
 * AlgoBotFrontendData. This module only renders broker-specific capabilities.
 */
(() => {
  'use strict';
  if (window.__algoBotBrokerNativeMarket) return;
  window.__algoBotBrokerNativeMarket = true;

  const $=(s,r=document)=>r.querySelector(s);
  const esc=v=>String(v??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[c]));
  const list=v=>window.AlgoBotFrontendData?.list?.(v)||[];
  const api=(url,options={},timeout=12000)=>window.AlgoBotFrontendData?.request?.(url,options,timeout);
  let contracts=[],capabilitiesRequest=0;

  const directionFor=type=>/PUT|FALL|LOWER|MULTDOWN|DIGITUNDER|NOTOUCH|TURBOSSHORT|RUNLOW|EXPIRYMISS/i.test(String(type||''))?'SELL':'BUY';
  const setStatus=message=>$('[data-contract-status]')?.replaceChildren(document.createTextNode(String(message||'')));
  const setPreparedDirection=direction=>{const normalized=String(direction||'').toUpperCase();if(!['BUY','SELL'].includes(normalized))return;[$('[data-direct-buy]'),$('[data-direct-sell]')].filter(Boolean).forEach(button=>{const active=String(button.dataset.direction||'').toUpperCase()===normalized;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active))});window.__algobotPreparedManualDirection=normalized;window.dispatchEvent(new CustomEvent('algobot:broker-direction-prepared',{detail:{direction:normalized}}))};
  function renderContracts(payload){
    const root=payload?.contracts_for||payload?.data?.contracts_for||payload;
    const raw=Array.isArray(payload)?payload:(payload?.contracts||payload?.available||root?.available||[]);
    contracts=raw.filter(c=>c&&c.contract_type).map(c=>({...c,contract_type:String(c.contract_type),contract_category:String(c.contract_category||''),expiry_type:String(c.expiry_type||''),underlying_symbol:String(c.underlying_symbol||$('#symbol')?.value||'')}));
    const select=$('[data-contract-type]'),typeLabel=$('[data-broker-trade-type]');if(!select)return;
    if(!contracts.length){select.innerHTML='<option value="">No broker contracts available</option>';select.disabled=true;if(typeLabel)typeLabel.textContent='Unavailable';setStatus('Deriv reports no contracts for this instrument');return}
    const previous=select.value;select.innerHTML=contracts.map(c=>`<option value="${esc(c.contract_type)}">${esc(c.contract_type+(c.contract_category?` · ${c.contract_category}`:''))}</option>`).join('');select.disabled=false;select.value=contracts.some(c=>c.contract_type===previous)?previous:contracts[0].contract_type;applyContract(select.value);setStatus(`${contracts.length} broker-supported contract type${contracts.length===1?'':'s'}`);
  }
  function applyContract(type){const selected=contracts.find(c=>String(c.contract_type)===String(type));if(!selected)return;setPreparedDirection(directionFor(selected.contract_type));const label=$('[data-broker-trade-type]');if(label)label.textContent=selected.contract_category||selected.contract_type||'Broker contract';window.__algobotSelectedBrokerContract=selected;window.__algobotAiOrderContext={...(window.__algobotAiOrderContext||{}),broker_source:'connected_broker',contract_type:selected.contract_type,contract_category:selected.contract_category||'',expiry_type:selected.expiry_type||'',underlying_symbol:selected.underlying_symbol||$('#symbol')?.value||'',sentiment:selected.sentiment||'',market:selected.market||'',submarket:selected.submarket||''};window.dispatchEvent(new CustomEvent('algobot:broker-contract-selected',{detail:selected}))}
  async function loadCapabilities(symbol){const requestId=++capabilitiesRequest,select=$('[data-contract-type]');if(!select||!symbol)return;select.disabled=true;select.innerHTML='<option value="">Loading broker contracts…</option>';if($('[data-broker-trade-type]'))$('[data-broker-trade-type]').textContent='Loading';setStatus('Loading broker-supported contracts…');try{const payload=await api(`/api/market/broker-capabilities/?symbol=${encodeURIComponent(symbol)}`,{notifyOnError:false},12000);if(requestId!==capabilitiesRequest)return;renderContracts(payload)}catch(error){if(requestId!==capabilitiesRequest)return;contracts=[];select.innerHTML='<option value="">Broker contracts unavailable</option>';select.disabled=true;if($('[data-broker-trade-type]'))$('[data-broker-trade-type]').textContent='Unavailable';setStatus(error?.message||'Broker capability request failed')}}
  const currentSymbol=()=>String($('#symbol')?.value||'').trim();
  const triggerCurrentSymbol=()=>{const symbol=currentSymbol();if(symbol)void loadCapabilities(symbol)};
  function boot(){if(!$('.terminal-page'))return;const symbol=$('#symbol'),contract=$('[data-contract-type]');symbol?.addEventListener('change',()=>loadCapabilities(symbol.value));contract?.addEventListener('change',()=>applyContract(contract.value));window.addEventListener('algobot:broker-symbols-loaded',triggerCurrentSymbol);window.addEventListener('algobot:market-symbol-changed',triggerCurrentSymbol);window.addEventListener('algobot:account-changed',triggerCurrentSymbol);window.addEventListener('algobot:account-synced',triggerCurrentSymbol);if(currentSymbol())triggerCurrentSymbol()}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
