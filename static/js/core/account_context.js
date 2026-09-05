/* AlgoBot canonical account selector. One server-authoritative browser state. */
(() => {
  'use strict';
  if (window.AlgoBotAccountContext) return;
  const STORAGE_KEY='algobot:selected-account-id:v1';
  const STORAGE_ACCOUNT_KEY='algobot:selected-account-snapshot:v1';
  const list=value=>Array.isArray(value)?value:(Array.isArray(value?.results)?value.results:(Array.isArray(value?.accounts)?value.accounts:[]));
  let accounts=[],selected=null,busy=null;
  const storageGet=()=>{try{return localStorage.getItem(STORAGE_KEY)}catch(_){return null}};
  const storageSet=id=>{try{id==null?localStorage.removeItem(STORAGE_KEY):localStorage.setItem(STORAGE_KEY,String(id))}catch(_){}};
  const snapshotGet=()=>{try{const raw=localStorage.getItem(STORAGE_ACCOUNT_KEY);const value=raw?JSON.parse(raw):null;return value&&value.id?value:null}catch(_){return null}};
  const snapshotSet=account=>{try{if(account?.id)localStorage.setItem(STORAGE_ACCOUNT_KEY,JSON.stringify({id:account.id,broker:account.broker,broker_name:account.broker_name,broker_account_id:account.broker_account_id,account_id:account.account_id,account_type:account.account_type,currency:account.currency,is_connected:account.is_connected,switch_enabled:account.switch_enabled}));else localStorage.removeItem(STORAGE_ACCOUNT_KEY)}catch(_){}};
  const accountId=a=>a?.id==null?null:String(a.id);
  const canonical=()=>window.AlgoBotFrontendData?.request;
  function publish(reason){window.AlgoBotBrokerState?.setAccount(selected,reason);window.dispatchEvent(new CustomEvent('algobot:account-context-changed',{detail:{account:selected,reason}}));window.dispatchEvent(new CustomEvent('algobot:account-changed',{detail:selected}));window.dispatchEvent(new CustomEvent('algobot:backend-accounts-loaded',{detail:accounts.slice()}))}
  function setSelected(account,reason='account-selected',persist=true){if(!account?.id)return null;selected=account;if(persist){storageSet(account.id);snapshotSet(account)}publish(reason);return account}
  async function load(force=false){
    if(busy&&!force)return busy;const request=canonical();if(!request)return selected;
    busy=(async()=>{
      const rememberedId=storageGet();
      const rememberedSnapshot=snapshotGet();
      const activeOptions={notifyOnError:false};
      if(rememberedId)activeOptions.headers={'X-Algobot-Account-ID':String(rememberedId)};
      const [accountsResult,activeResult]=await Promise.allSettled([
        request('/api/brokers/accounts/',{notifyOnError:false},10000),
        request('/api/brokers/accounts/active/',activeOptions,8000),
      ]);
      const listSucceeded=accountsResult.status==='fulfilled';
      const activeSucceeded=activeResult.status==='fulfilled';
      const rows=listSucceeded?list(accountsResult.value).filter(a=>a?.id):[];
      accounts=rows;
      window.AlgoBotBrokerAccounts=rows.slice();
      const serverSelected=activeSucceeded?(activeResult.value?.active_account||activeResult.value?.account||null):null;
      const serverId=accountId(serverSelected);
      // A successful backend response is authoritative. Local storage is used
      // only for degraded transport recovery after an account read fails.
      let target=(serverId&&rows.find(a=>accountId(a)===serverId))||serverSelected||rows.find(a=>a.is_active===true)||((rows.length===1&&rows[0]?.is_connected===true)?rows[0]:null);
      if(!target&&(!listSucceeded||!activeSucceeded)){
        target=(rememberedId&&rows.find(a=>accountId(a)===String(rememberedId)))||null;
      }
      if(!target&&(!listSucceeded||!activeSucceeded)&&rememberedSnapshot&&accountId(rememberedSnapshot)===String(rememberedId||rememberedSnapshot.id)){
        target=rememberedSnapshot;
        accounts=[rememberedSnapshot];
        window.AlgoBotBrokerAccounts=accounts.slice();
      }
      if(!target){selected=null;storageSet(null);snapshotSet(null);window.AlgoBotBrokerState?.reset('no-connected-broker-account');window.dispatchEvent(new CustomEvent('algobot:backend-accounts-loaded',{detail:accounts.slice()}));if(!listSucceeded&&accountsResult.reason)throw accountsResult.reason;if(!activeSucceeded&&activeResult.reason)throw activeResult.reason;return null}
      const hydrated=serverSelected&&accountId(serverSelected)===accountId(target)?serverSelected:target;
      accounts=accounts.map(a=>accountId(a)===accountId(hydrated)?{...a,...hydrated,is_active:true}:{...a,is_active:false,is_preferred:false});
      if(!accounts.some(a=>accountId(a)===accountId(hydrated)))accounts=[hydrated,...accounts];
      window.AlgoBotBrokerAccounts=accounts.slice();
      const degraded=!listSucceeded||!activeSucceeded;
      return setSelected(hydrated,degraded?'account-context-degraded':(activeSucceeded?'account-context-hydrated':'account-context-recovered'),true);
    })().finally(()=>{busy=null});return busy;
  }
  async function selectAccount(id){
    if(busy)await busy.catch(()=>{});const target=accounts.find(a=>accountId(a)===String(id));if(!target)throw new Error('The selected broker account is no longer available. Refresh the account list.');if(target.switch_enabled===false)throw new Error('Broker account switching is disabled by platform configuration.');const request=canonical();if(!request)throw new Error('The broker account service is not ready.');const requestedType=String(target.account_type||target.credentials?.account_type||'').toLowerCase();const payload=['demo','real'].includes(requestedType)?{account_type:requestedType}:{};const confirmedResponse=await request(`/api/brokers/accounts/${encodeURIComponent(target.id)}/select/`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),notifyOnError:false},8000);const confirmed=confirmedResponse?.active_account||confirmedResponse?.account;if(!confirmed?.id||accountId(confirmed)!==accountId(target))throw new Error('Broker did not confirm the selected account.');accounts=accounts.map(a=>accountId(a)===accountId(confirmed)?confirmed:{...a,is_preferred:false,is_active:false});window.AlgoBotBrokerAccounts=accounts.slice();return setSelected(confirmed,'account-switch',true);
  }
  function getSelected(){return selected||window.AlgoBotBrokerState?.get?.().account||null}
  function getSelectedId(){return accountId(getSelected())||null}
  function getAccounts(){return accounts.slice()}
  window.AlgoBotAccountContext=Object.freeze({load,refresh:()=>load(true),selectAccount,getSelected,getSelectedId,getAccounts});
  document.addEventListener('click',event=>{const b=event.target?.closest?.('[data-account-switch]');if(b){event.preventDefault();event.stopImmediatePropagation();const explicit=b.dataset.accountId||b.dataset.accountTarget,current=getSelectedId(),target=explicit?accounts.find(a=>accountId(a)===String(explicit)):accounts.find(a=>accountId(a)!==String(current));if(target)selectAccount(target.id).catch(error=>window.dispatchEvent(new CustomEvent('algobot:account-context-error',{detail:error})));return}const g=event.target?.closest?.('[data-select]');if(g){event.preventDefault();event.stopImmediatePropagation();selectAccount(g.dataset.select).catch(error=>window.dispatchEvent(new CustomEvent('algobot:account-context-error',{detail:error}))) }},true);
  window.addEventListener('algobot:backend-accounts-loaded',event=>{const rows=list(event.detail).filter(a=>a?.id);if(rows.length)accounts=rows;if(selected&&accounts.some(a=>accountId(a)===accountId(selected)))return;if(!selected){const target=accounts.find(a=>a.is_active===true||a.is_default===true||a.is_preferred===true);if(target)setSelected(target,'backend-accounts-rehydrated',false)}});
  window.addEventListener('algobot:account-synced',event=>{if(!event.detail?.id)return;const id=accountId(event.detail);accounts=accounts.map(a=>accountId(a)===id?event.detail:a);if(getSelectedId()===id)setSelected(event.detail,'account-synced',true)});
  window.addEventListener('algobot:account-context-error',event=>{const message=event.detail?.message||'Broker account selection is temporarily unavailable.';window.dispatchEvent(new CustomEvent('algobot:api-error',{detail:{code:'ACCOUNT_CONTEXT_ERROR',status:0,message,retryable:true}}))});
  const boot=()=>{if(document.body.dataset.authenticated==='true')load().catch(error=>window.dispatchEvent(new CustomEvent('algobot:account-context-error',{detail:error})))};if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
