/* AlgoBot Unified Service Runtime. Cross-service browser infrastructure lives here. */
(() => {
  'use strict';
  if (window.AlgoBotServiceRuntime) return;
  const active=new Map(),controllers=new Map(),registry=new Map(),errors=[]; const MAX_ERRORS=100;
  const now=()=>new Date().toISOString();
  const accountId=()=>String(window.AlgoBotAccountContext?.getSelectedId?.()||window.AlgoBotBrokerState?.get?.()?.account?.id||'');
  const emit=(name,detail={})=>window.dispatchEvent(new CustomEvent(name,{detail:{...detail,at:now(),accountId:accountId()}}));
  const register=(name,config={})=>{if(!name)throw new Error('A service name is required.');const value={...(registry.get(name)||{}),...config,name,registeredAt:(registry.get(name)||{}).registeredAt||now()};registry.set(name,value);emit('algobot:service-registered',{service:value});return Object.freeze({...value});};
  const begin=(name,label='Loading…')=>{active.set(name,(active.get(name)||0)+1);document.documentElement.dataset.algobotBusy='true';emit('algobot:service-loading',{service:name,label,count:active.get(name)});return()=>end(name)};
  const end=name=>{const count=Math.max(0,(active.get(name)||0)-1);count?active.set(name,count):active.delete(name);if(!active.size)delete document.documentElement.dataset.algobotBusy;emit('algobot:service-idle',{service:name,count});};
  const retryable=e=>Boolean(e&&(e.retryable??(['NETWORK_ERROR','API_TIMEOUT','SERVICE_TIMEOUT'].includes(e.code)||Number(e.status)>=500)));
  async function withTimeout(task,timeout=25000,name='service'){const key=`${name}:${Date.now()}:${Math.random()}`,controller=new AbortController();controllers.set(key,controller);let timer;try{return await Promise.race([Promise.resolve().then(()=>task({signal:controller.signal})),new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();const e=new Error(`${name} timed out after ${timeout}ms.`);e.code='SERVICE_TIMEOUT';e.service=name;e.retryable=true;reject(e)},Math.max(1000,timeout))})])}finally{clearTimeout(timer);controllers.delete(key)}}
  async function run(name,task,{timeout=25000,retry=0,retryDelay=1000,label='Loading…'}={}){const release=begin(name,label);try{for(let attempt=0;attempt<=retry;attempt++){try{return await withTimeout(task,timeout,name)}catch(e){if(attempt>=retry||!retryable(e))throw e;await new Promise(r=>setTimeout(r,retryDelay*(attempt+1)))}}}finally{release()}}
  const cancel=name=>{for(const[key,c]of controllers)if(key.startsWith(`${name}:`))c.abort();emit('algobot:service-cancelled',{service:name})};
  const recordError=detail=>{const e={at:now(),service:detail.service||'unknown',url:detail.url||'',method:detail.method||'GET',status:Number(detail.status||0),code:detail.code||'UNKNOWN_ERROR',message:detail.message||'Request failed.',accountId:accountId(),retryable:Boolean(detail.retryable)};errors.push(e);if(errors.length>MAX_ERRORS)errors.shift();emit('algobot:service-error',{error:e});return e};
  const snapshot=()=>({accountId:accountId(),services:[...registry.values()].map(v=>({...v})),loading:Object.fromEntries(active),errors:errors.slice(-20)});
  window.AlgoBotServiceRuntime=Object.freeze({register,begin,end,run,withTimeout,cancel,isRetryable:retryable,recordError,recentErrors:n=>errors.slice(-Math.max(1,n||20)),snapshot,accountId});
  window.addEventListener('algobot:api-error',e=>{const detail=e.detail||{},entry=recordError(detail);window.dispatchEvent(new CustomEvent('algobot:recoverable-error',{detail:entry}))});
  const reset=()=>{active.clear();delete document.documentElement.dataset.algobotBusy;emit('algobot:services-account-reset')};
  window.addEventListener('algobot:account-changed',reset);window.addEventListener('algobot:account-context-changed',reset);
  window.addEventListener('algobot:recoverable-error',e=>{const d=e.detail||{};document.querySelectorAll('[data-global-error]').forEach(el=>{el.textContent=d.message||'The service is temporarily unavailable. Please try again.';el.hidden=false});document.querySelectorAll('[data-service-retry]').forEach(el=>{el.hidden=!d.retryable;el.dataset.retryService=d.service||''})});
  emit('algobot:service-runtime-ready',{version:1});
})();
