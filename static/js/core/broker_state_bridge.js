/* Canonical broker/account synchronization bridge.
 * Account selection itself is owned by account_context.js; this module only
 * reconciles that selected account with authoritative backend/broker state.
 */
(() => {
  'use strict';
  if (window.__algoBotBrokerStateBridge) return;
  window.__algoBotBrokerStateBridge = true;
  const CONNECT_TIMEOUT_MS=40000,RETRY_INTERVAL_MS=10000,HEALTH_REFRESH_MS=30000;
  let lastAccountId=null,lastConnection=null,lastBalance=null,knownAccounts=[],timer=null,syncPromise=null,forceSnapshotSyncForId=null,syncGeneration=0,syncAgain=false;
  const list=v=>Array.isArray(v)?v:(Array.isArray(v?.results)?v.results:(Array.isArray(v?.data)?v.data:(Array.isArray(v?.accounts)?v.accounts:[])));
  const csrf=()=>document.querySelector('meta[name="csrf-token"]')?.content||document.cookie.split(';').map(v=>v.trim()).find(v=>v.startsWith('csrftoken='))?.split('=').slice(1).join('=')||'';
  async function requestJson(url,options={},timeoutMs=25000){const frontendData=window.AlgoBotFrontendData;if(frontendData?.request){try{return await frontendData.request(url,{notifyOnError:false,...options},timeoutMs)}catch(error){if(error?.code==='API_TIMEOUT')error.code='BROKER_SYNC_TIMEOUT';throw error}}const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),timeoutMs);try{const response=await fetch(url,{credentials:'same-origin',headers:{Accept:'application/json',...(options.headers||{})},cache:'no-store',signal:controller.signal,...options});let payload=null;try{payload=await response.json()}catch(_){}if(!response.ok){const e=new Error(payload?.detail||payload?.message||`Broker request failed (${response.status})`);e.status=response.status;e.payload=payload;throw e}return payload}catch(error){if(error?.name==='AbortError')error.code='BROKER_SYNC_TIMEOUT';throw error}finally{clearTimeout(timeout)}}
  async function refreshAccounts(store,generation){
    const context=window.AlgoBotAccountContext;
    if(!context?.load)throw new Error('Canonical broker account context is not ready.');
    await context.load();
    if(generation!==syncGeneration)return null;
    const accounts=list(context.getAccounts?.()).filter(a=>a?.id);
    knownAccounts=accounts;
    window.AlgoBotBrokerAccounts=accounts.slice();
    const account=context.getSelected?.()||null;
    window.dispatchEvent(new CustomEvent('algobot:backend-accounts-loaded',{detail:accounts.slice()}));
    if(!account){if(!store.get().account)store.reset('backend-no-broker-account');return store.get().account||null}
    const id=String(account.id),connected=account.status==='active'&&account.is_connected===true,balance=String(account.balance??'');
    const current=store.get();
    if(!current.account||id!==lastAccountId||connected!==lastConnection||balance!==lastBalance)store.setAccount(account,'backend-broker-account');
    lastAccountId=id;lastConnection=connected;lastBalance=balance;
    window.dispatchEvent(new CustomEvent('algobot:backend-account-loaded',{detail:account}));
    return account;
  }
  async function syncAccountSnapshot(store,account,generation){
    const id=String(account.id);
    const payload=await requestJson('/api/brokers/accounts/'+encodeURIComponent(id)+'/sync/',{
      method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()}
    },16000);
    if(generation!==syncGeneration)return window.AlgoBotAccountContext?.getSelected?.()||null;
    const synced=payload?.account;
    if(!synced||String(synced.id)!==id)throw new Error('Broker snapshot sync did not confirm the selected account.');
    forceSnapshotSyncForId=null;
    store.setAccount(synced,'broker-account-snapshot-synced');
    window.dispatchEvent(new CustomEvent('algobot:account-synced',{detail:synced}));
    return synced;
  }
  async function verifyWithBroker(store,account,generation){
    if(generation!==syncGeneration)return window.AlgoBotAccountContext?.getSelected?.()||null;
    if(!account?.id||!account?.broker)return account;
    if(account.credential_status==='credentials_unavailable'||account.credential_status==='credentials_expired'){
      const message=account.credential_status==='credentials_expired'?'Broker credentials have expired. Reconnect your broker account.':'Broker credentials are unavailable. Reconnect your broker account.';
      store.transition(store.STATES.ERROR,{account,lastError:message},'broker-credentials-unavailable');return account;
    }
    if(account.status==='active'&&account.is_connected===true){
      store.setAccount(account,'broker-already-connected');
      const syncedAt=Date.parse(account.last_synced_at||'');
      const snapshotNeedsSync=forceSnapshotSyncForId===String(account.id)||!Number.isFinite(syncedAt)||(Date.now()-syncedAt)>60000;
      if(!snapshotNeedsSync)return account;
      store.transition(store.STATES.SYNCING,{account},'broker-account-snapshot-sync-started');
      try{return await syncAccountSnapshot(store,account,generation)}
      catch(error){
        if(generation!==syncGeneration)return window.AlgoBotAccountContext?.getSelected?.()||null;
        store.transition(store.STATES.DEGRADED,{account,lastError:'Broker connection is verified, but its financial snapshot could not be refreshed.'},'broker-account-snapshot-sync-failed');
        window.dispatchEvent(new CustomEvent('algobot:account-sync-error',{detail:{error,account}}));return account;
      }
    }
    store.transition(store.STATES.SYNCING,{account},'broker-live-connection-started');
    try{
      const payload=await requestJson('/api/brokers/connect/',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify({broker_id:account.broker.id,account_id:account.id})},CONNECT_TIMEOUT_MS);
      if(generation!==syncGeneration)return window.AlgoBotAccountContext?.getSelected?.()||null;
      const verified=payload?.account;
      if(!verified)throw new Error('Backend broker connection returned no account payload.');
      store.setAccount(verified,'broker-live-connected');
      window.dispatchEvent(new CustomEvent('algobot:account-synced',{detail:verified}));
      return await syncAccountSnapshot(store,verified,generation);
    }catch(error){
      if(generation!==syncGeneration)return window.AlgoBotAccountContext?.getSelected?.()||null;
      const current=store.get(),bs=error.payload?.broker_status;
      const state=(error.status===401||bs==='credentials_expired')?store.STATES.ERROR:(error.status===409?store.STATES.DISCONNECTED:(error.status===503||error.status===504||bs==='unavailable'||bs==='sync_timeout'||error.code==='BROKER_SYNC_TIMEOUT'?store.STATES.DEGRADED:store.STATES.ERROR));
      store.transition(state,{account:current.account||account,lastError:error.code==='BROKER_SYNC_TIMEOUT'?'Broker connection timed out; retrying.':error.message},'broker-live-connection-failed');
      window.dispatchEvent(new CustomEvent('algobot:account-sync-error',{detail:{error,account:current.account||account}}));return current.account||account;
    }
  }
  function syncFromBackend(){
    const store=window.AlgoBotBrokerState;
    if(!store||document.body.dataset.authenticated!=='true')return Promise.resolve(store?.get?.().account||null);
    if(syncPromise){syncAgain=true;return syncPromise;}
    const generation=syncGeneration;
    syncPromise=(async()=>{
      try{
        const account=await refreshAccounts(store,generation);
        if(generation!==syncGeneration)return window.AlgoBotAccountContext?.getSelected?.()||null;
        return account?await verifyWithBroker(store,account,generation):null;
      }catch(error){
        if(generation!==syncGeneration)return window.AlgoBotAccountContext?.getSelected?.()||null;
        const current=store.get();
        store.transition(current.account?store.STATES.DEGRADED:store.STATES.ERROR,{account:current.account,lastError:error.message},'backend-broker-account-error');
        window.dispatchEvent(new CustomEvent('algobot:account-context-error',{detail:error}));
        return current.account||null;
      }finally{
        syncPromise=null;
        if(syncAgain){syncAgain=false;Promise.resolve().then(syncFromBackend);}
      }
    })();
    return syncPromise;
  }
  function schedule(){if(timer)clearInterval(timer);const start=()=>{if(!window.AlgoBotBrokerState||!window.AlgoBotAccountContext){setTimeout(start,250);return}syncFromBackend();timer=setInterval(syncFromBackend,RETRY_INTERVAL_MS);setTimeout(()=>{if(timer)clearInterval(timer);timer=setInterval(syncFromBackend,HEALTH_REFRESH_MS)},RETRY_INTERVAL_MS*3)};start()}
  window.AlgoBotBrokerSync=syncFromBackend;
  window.addEventListener('algobot:account-switch-started',()=>{syncGeneration+=1;syncAgain=false;});
  window.addEventListener('algobot:account-changed',event=>{
    if(event.detail?.id==null)return;
    syncGeneration+=1;
    const syncedAt=Date.parse(event.detail.last_synced_at||'');
    const recentlySynced=event.detail.is_connected===true&&Number.isFinite(syncedAt)&&(Date.now()-syncedAt)<60000;
    forceSnapshotSyncForId=recentlySynced?null:String(event.detail.id);
    window.AlgoBotBrokerState?.setAccount(event.detail,'account-changed');
    syncFromBackend().catch(()=>{});
  });
  window.addEventListener('algobot:account-synced',event=>{if(!event.detail)return;window.AlgoBotBrokerState?.setAccount(event.detail,'account-synced');knownAccounts=knownAccounts.map(a=>String(a.id)===String(event.detail.id)?event.detail:a);window.AlgoBotBrokerAccounts=knownAccounts.slice()});
  window.addEventListener('algobot:account-sync-error',event=>{if(window.AlgoBotBrokerState){const s=window.AlgoBotBrokerState.get();window.AlgoBotBrokerState.transition(window.AlgoBotBrokerState.STATES.DEGRADED,{account:s.account,lastError:event.detail?.error?.message||'Broker connection failed; retrying.'},'account-sync-error')}});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',schedule,{once:true});else schedule();
})();
