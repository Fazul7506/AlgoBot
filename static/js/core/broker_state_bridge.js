/* Canonical browser bridge: backend account + verified live broker data are authoritative. */
(() => {
  'use strict';
  if (window.__algoBotBrokerStateBridge) return;
  window.__algoBotBrokerStateBridge = true;

  const CONNECT_TIMEOUT_MS = 40000;
  const RETRY_INTERVAL_MS = 10000;
  const HEALTH_REFRESH_MS = 30000;
  let lastAccountId = null, lastConnection = null, lastBalance = null;
  let knownAccounts = [], timer = null, syncPromise = null;
  const list = value => Array.isArray(value) ? value : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));
  const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || document.cookie.split(';').map(v => v.trim()).find(v => v.startsWith('csrftoken='))?.split('=').slice(1).join('=') || '';

  async function requestJson(url, options = {}, timeoutMs = 25000) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, { credentials:'same-origin', headers:{Accept:'application/json',...(options.headers||{})}, cache:'no-store', signal:controller.signal, ...options });
      let payload = null; try { payload = await response.json(); } catch (_) {}
      if (!response.ok) {
        const detail=payload?.detail || `Broker request failed (${response.status})`;
        const error=new Error(detail); error.status=response.status; error.payload=payload; throw error;
      }
      return payload;
    } catch (error) {
      if (error?.name === 'AbortError' || error?.name === 'AlgoBotTimeoutError') error.code='BROKER_SYNC_TIMEOUT';
      throw error;
    } finally { clearTimeout(timeout); }
  }

  async function refreshAccounts(store) {
    const accounts=list(await requestJson('/api/brokers/accounts/')).filter(a=>a?.id);
    knownAccounts=accounts; window.AlgoBotBrokerAccounts=accounts.slice();
    window.dispatchEvent(new CustomEvent('algobot:backend-accounts-loaded',{detail:accounts.slice()}));
    const account=accounts.find(a=>a.is_preferred||a.is_default)||accounts[0]||null;
    if(!account){ if(!store.get().account) store.reset('backend-no-broker-account'); return store.get().account||null; }
    const id=String(account.id), connected=account.status==='active'&&account.is_connected===true, balance=String(account.balance??'');
    const current=store.get();
    if(!current.account||id!==lastAccountId||connected!==lastConnection||balance!==lastBalance) store.setAccount(account,'backend-broker-account');
    lastAccountId=id; lastConnection=connected; lastBalance=balance;
    window.dispatchEvent(new CustomEvent('algobot:backend-account-loaded',{detail:account}));
    return account;
  }

  async function verifyWithBroker(store, account) {
    if(!account?.id||!account?.broker) return account;
    if(account.credential_status==='credentials_unavailable'||account.credential_status==='credentials_expired'){
      const message=account.credential_status==='credentials_expired'?'Broker credentials have expired. Reconnect your broker account.':'Broker credentials are unavailable. Reconnect your broker account.';
      store.transition(store.STATES.ERROR,{account,lastError:message},'broker-credentials-unavailable'); return account;
    }

    // The account serializer is authoritative. If a real BrokerConnection is
    // already connected, do not tear it down/reconnect on every dashboard poll.
    if(account.status==='active' && account.is_connected===true){
      store.setAccount(account,'broker-already-connected');
      return account;
    }

    store.transition(store.STATES.SYNCING,{account},'broker-live-connection-started');
    try{
      // OAuth proves authorization; this endpoint creates the actual account-
      // scoped live BrokerConnection. It is deliberately the same backend path
      // used by every broker connection flow.
      const payload=await requestJson('/api/brokers/connect/',{
        method:'POST',
        headers:{'Content-Type':'application/json','X-CSRFToken':csrfToken()},
        body:JSON.stringify({broker_id:account.broker.id,account_id:account.id})
      },CONNECT_TIMEOUT_MS);
      const verified=payload?.account; if(!verified) throw new Error('Backend broker connection returned no account payload.');
      store.setAccount(verified,'broker-live-connected');
      window.dispatchEvent(new CustomEvent('algobot:account-synced',{detail:verified}));
      return verified;
    }catch(error){
      const brokerStatus=error.payload?.broker_status, current=store.get();
      const state=(error.status===401||brokerStatus==='credentials_expired')?store.STATES.ERROR:(error.status===409?store.STATES.DISCONNECTED:(error.status===503||error.status===504||brokerStatus==='unavailable'||brokerStatus==='sync_timeout'||error.code==='BROKER_SYNC_TIMEOUT'?store.STATES.DEGRADED:store.STATES.ERROR));
      store.transition(state,{account:current.account||account,lastError:error.code==='BROKER_SYNC_TIMEOUT'?'Broker connection timed out; retrying.':error.message},'broker-live-connection-failed');
      window.dispatchEvent(new CustomEvent('algobot:account-sync-error',{detail:{error,account:current.account||account}}));
      return current.account||account;
    }
  }

  function syncFromBackend(accountId=null){
    const store=window.AlgoBotBrokerState;
    if(!store) return Promise.resolve(null);
    if(document.body.dataset.authenticated!=='true') return Promise.resolve(store.get()?.account||null);
    if(syncPromise) return syncPromise;
    syncPromise=(async()=>{
      try{
        const account=accountId ? knownAccounts.find(a=>String(a.id)===String(accountId)) || {id:accountId,broker:true} : await refreshAccounts(store);
        return account ? await verifyWithBroker(store,account) : null;
      }catch(error){ const current=store.get(); store.transition(current.account?store.STATES.DEGRADED:store.STATES.ERROR,{account:current.account,lastError:error.message},'backend-broker-account-error'); return current.account||null; }
      finally{ syncPromise=null; }
    })();
    return syncPromise;
  }

  function schedule(){
    if(timer) clearInterval(timer);
    const start=()=>{
      if(!window.AlgoBotBrokerState){ setTimeout(start,250); return; }
      syncFromBackend();
      // Retry quickly while disconnected; once connected, polling only refreshes
      // the authoritative account state and never starts a duplicate connection.
      timer=setInterval(()=>syncFromBackend(),RETRY_INTERVAL_MS);
      setTimeout(()=>{
        if(timer) clearInterval(timer);
        timer=setInterval(()=>syncFromBackend(),HEALTH_REFRESH_MS);
      },RETRY_INTERVAL_MS * 3);
    };
    start();
  }
  window.AlgoBotBrokerSync=syncFromBackend;
  window.addEventListener('algobot:account-changed',event=>{if(window.AlgoBotBrokerState&&event.detail)window.AlgoBotBrokerState.setAccount(event.detail,'account-changed');knownAccounts=knownAccounts.map(a=>String(a.id)===String(event.detail?.id)?event.detail:{...a,is_preferred:false});window.AlgoBotBrokerAccounts=knownAccounts.slice();syncFromBackend(event.detail?.id);});
  window.addEventListener('algobot:account-synced',event=>{if(window.AlgoBotBrokerState&&event.detail)window.AlgoBotBrokerState.setAccount(event.detail,'account-synced');knownAccounts=knownAccounts.map(a=>String(a.id)===String(event.detail?.id)?event.detail:a);window.AlgoBotBrokerAccounts=knownAccounts.slice();});
  window.addEventListener('algobot:account-sync-error',event=>{if(window.AlgoBotBrokerState){const s=window.AlgoBotBrokerState.get();window.AlgoBotBrokerState.transition(window.AlgoBotBrokerState.STATES.DEGRADED,{account:s.account,lastError:event.detail?.error?.message||'Broker connection failed; retrying.'},'account-sync-error');}});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',schedule,{once:true});else schedule();
})();