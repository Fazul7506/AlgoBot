/* AlgoBot canonical account selector.
 * One browser selection state, persisted for navigation/refresh, reconciled with
 * the authenticated server session, and broadcast to every page module.
 */
(() => {
  'use strict';
  if (window.AlgoBotAccountContext) return;

  const STORAGE_KEY='algobot:selected-account-id:v1';
  const list=value=>Array.isArray(value)?value:(Array.isArray(value?.results)?value.results:(Array.isArray(value?.accounts)?value.accounts:[]));
  let accounts=[],selected=null,busy=null;
  const storageGet=()=>{try{return localStorage.getItem(STORAGE_KEY)}catch(_){return null}};
  const storageSet=id=>{try{id==null?localStorage.removeItem(STORAGE_KEY):localStorage.setItem(STORAGE_KEY,String(id))}catch(_){}};
  const accountId=a=>a?.id==null?null:String(a.id);
  const canonical=()=>window.AlgoBotFrontendData?.request;

  function publish(reason){
    window.AlgoBotBrokerState?.setAccount(selected,reason);
    window.dispatchEvent(new CustomEvent('algobot:account-context-changed',{detail:{account:selected,reason}}));
    window.dispatchEvent(new CustomEvent('algobot:account-changed',{detail:selected}));
    window.dispatchEvent(new CustomEvent('algobot:backend-accounts-loaded',{detail:accounts.slice()}));
  }
  function setSelected(account,reason='account-selected',persist=true){
    if(!account?.id)return null;
    selected=account;if(persist)storageSet(account.id);publish(reason);return account;
  }

  async function confirmServerSelection(target){
    const request=canonical();
    if(!request||!target?.id)return null;
    const requestedType=String(target.account_type||target.credentials?.account_type||'').toLowerCase();
    if(!['demo','real'].includes(requestedType))return null;
    const result=await request(`/api/brokers/accounts/${encodeURIComponent(target.id)}/select/`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_type:requestedType}),notifyOnError:false},8000);
    return result?.active_account||result?.account||null;
  }

  async function load(force=false){
    if(busy&&!force)return busy;
    const request=canonical();if(!request)return selected;
    busy=(async()=>{
      const rows=list(await request('/api/brokers/accounts/',{notifyOnError:false},10000)).filter(a=>a?.id);
      accounts=rows;window.AlgoBotBrokerAccounts=rows.slice();
      const storedId=storageGet();
      const target=(storedId&&rows.find(a=>accountId(a)===storedId))||rows.find(a=>a.is_preferred||a.is_default||a.is_active)||rows[0]||null;
      if(!target){selected=null;storageSet(null);window.AlgoBotBrokerState?.reset('no-connected-broker-account');return null}
      try{
        const confirmed=await confirmServerSelection(target);
        if(confirmed?.id){
          accounts=accounts.map(a=>accountId(a)===accountId(confirmed)?confirmed:{...a,is_preferred:false,is_active:false});
          window.AlgoBotBrokerAccounts=accounts.slice();
          return setSelected(confirmed,'account-context-hydrated',true);
        }
      }catch(error){
        // A failed reconciliation must not destroy a valid local selection. The
        // service layer reports the error; page data remains account-isolated.
        window.dispatchEvent(new CustomEvent('algobot:account-context-reconcile-failed',{detail:{accountId:target.id,error}}));
      }
      return setSelected(target,'account-context-hydrated',true);
    })().finally(()=>{busy=null});
    return busy;
  }

  async function selectAccount(id){
    if(busy)await busy.catch(()=>{});
    const target=accounts.find(a=>accountId(a)===String(id));
    if(!target)throw new Error('The selected broker account is no longer available. Refresh the account list.');
    if(target.switch_enabled===false)throw new Error('Broker account switching is disabled by platform configuration.');
    const confirmed=await confirmServerSelection(target);
    if(!confirmed?.id||accountId(confirmed)!==accountId(target))throw new Error('Broker did not confirm the selected account.');
    accounts=accounts.map(a=>accountId(a)===accountId(confirmed)?confirmed:{...a,is_preferred:false,is_active:false});
    window.AlgoBotBrokerAccounts=accounts.slice();
    return setSelected(confirmed,'account-switch',true);
  }

  function getSelected(){return selected||window.AlgoBotBrokerState?.get?.().account||null}
  function getSelectedId(){return accountId(getSelected())||storageGet()}
  function getAccounts(){return accounts.slice()}
  window.AlgoBotAccountContext=Object.freeze({load,refresh:()=>load(true),selectAccount,getSelected,getSelectedId,getAccounts});

  // Compatibility for legacy account controls. Explicit target IDs always win;
  // an unspecified switch control toggles to the next available account.
  document.addEventListener('click',event=>{
    const switchButton=event.target?.closest?.('[data-account-switch]');
    if(switchButton){
      event.preventDefault();event.stopImmediatePropagation();
      const explicit=switchButton.dataset.accountId||switchButton.dataset.accountTarget;
      const currentId=getSelectedId();
      const target=explicit?accounts.find(a=>accountId(a)===String(explicit)):accounts.find(a=>accountId(a)!==String(currentId));
      if(target)selectAccount(target.id).catch(error=>window.dispatchEvent(new CustomEvent('algobot:account-context-error',{detail:error})));
      return;
    }
    const gridButton=event.target?.closest?.('[data-select]');
    if(gridButton){
      event.preventDefault();event.stopImmediatePropagation();
      selectAccount(gridButton.dataset.select).catch(error=>window.dispatchEvent(new CustomEvent('algobot:account-context-error',{detail:error})));
    }
  },true);

  window.addEventListener('algobot:backend-accounts-loaded',event=>{
    const rows=list(event.detail).filter(a=>a?.id);if(rows.length)accounts=rows;
    const id=storageGet(),target=id&&accounts.find(a=>accountId(a)===id);if(target&&accountId(selected)!==id)setSelected(target,'backend-accounts-rehydrated',false);
  });
  window.addEventListener('algobot:account-synced',event=>{if(!event.detail?.id)return;const id=accountId(event.detail);accounts=accounts.map(a=>accountId(a)===id?event.detail:a);if(getSelectedId()===id)setSelected(event.detail,'account-synced',true)});
  window.addEventListener('algobot:account-context-error',event=>{const message=event.detail?.message||'Broker account selection is temporarily unavailable.';window.dispatchEvent(new CustomEvent('algobot:api-error',{detail:{code:'ACCOUNT_CONTEXT_ERROR',status:0,message,retryable:true}}))});

  const boot=()=>{if(document.body.dataset.authenticated==='true')load().catch(error=>window.dispatchEvent(new CustomEvent('algobot:account-context-error',{detail:error}))) };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
