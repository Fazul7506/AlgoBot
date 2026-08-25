/* Canonical browser bridge: backend account + verified live broker data are authoritative. */
(() => {
  'use strict';
  if (window.__algoBotBrokerStateBridge) return;
  window.__algoBotBrokerStateBridge = true;

  let lastAccountId = null;
  let lastConnection = null;
  let lastBalance = null;
  let knownAccounts = [];
  let busy = false;
  let timer = null;

  const list = value => Array.isArray(value) ? value : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.data) ? value.data : []));
  const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || document.cookie.split(';').map(v => v.trim()).find(v => v.startsWith('csrftoken='))?.split('=').slice(1).join('=') || '';

  async function requestJson(url, options = {}, timeoutMs = 10000) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {credentials:'same-origin',headers:{Accept:'application/json',...(options.headers||{})},cache:'no-store',signal:controller.signal,...options});
      let payload = null;
      try { payload = await response.json(); } catch (_) {}
      if (!response.ok) {
        const detail = payload?.detail || `Broker request failed (${response.status})`;
        const error = new Error(detail); error.status=response.status; error.payload=payload; throw error;
      }
      return payload;
    } finally { clearTimeout(timeout); }
  }

  async function refreshAccounts(store) {
    const accounts = list(await requestJson('/api/brokers/accounts/')).filter(a => a?.id);
    knownAccounts = accounts;
    // Publish the exact backend list once so every widget reads the same
    // account selection instead of each one independently polling the API.
    window.AlgoBotBrokerAccounts = accounts.slice();
    window.dispatchEvent(new CustomEvent('algobot:backend-accounts-loaded', {detail: accounts.slice()}));
    const account = accounts.find(a => a.is_preferred || a.is_default) || accounts[0] || null;
    if (!account) {
      // Never destroy a known-good account because one polling request returned
      // an empty response during deployment/session startup.
      if (!store.get().account) store.reset('backend-no-broker-account');
      return store.get().account || null;
    }
    const id = String(account.id);
    const connected = account.status === 'active' && account.is_connected === true;
    const balance = String(account.balance ?? '');
    const current = store.get();
    if (!current.account || id !== lastAccountId || connected !== lastConnection || balance !== lastBalance) store.setAccount(account,'backend-broker-account');
    lastAccountId=id; lastConnection=connected; lastBalance=balance;
    window.dispatchEvent(new CustomEvent('algobot:backend-account-loaded',{detail:account}));
    return account;
  }

  async function verifyWithBroker(store, account) {
    if (!account?.id || !account?.broker) return;
    store.transition(store.STATES.SYNCING,{account},'broker-live-verification-started');
    try {
      const payload=await requestJson(`/api/brokers/accounts/${encodeURIComponent(account.id)}/sync/`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrfToken()}},10000);
      const verified=payload?.account;
      if (!verified) throw new Error('Backend broker synchronization returned no account payload.');
      store.setAccount(verified,'broker-live-verified');
      window.dispatchEvent(new CustomEvent('algobot:account-synced',{detail:verified}));
    } catch(error) {
      const brokerStatus=error.payload?.broker_status;
      const current=store.get();
      const state=(error.status===401 || brokerStatus==='credentials_expired') ? store.STATES.ERROR : (error.status===409 ? store.STATES.DISCONNECTED : (error.status===503 || error.status===504 || brokerStatus==='unavailable' || brokerStatus==='sync_timeout' ? store.STATES.DEGRADED : store.STATES.ERROR));
      // Preserve the account so the UI can report the actual broker failure
      // instead of pretending that no account exists.
      store.transition(state,{account:current.account || account,lastError:error.name==='AbortError'?'Broker synchronization timed out.':error.message},'broker-live-verification-failed');
      window.dispatchEvent(new CustomEvent('algobot:account-sync-error',{detail:{error,account:current.account || account}}));
    }
  }

  async function syncFromBackend() {
    const store=window.AlgoBotBrokerState;
    if (!store || document.body.dataset.authenticated!=='true' || busy) return;
    busy=true;
    try {
      const account=await refreshAccounts(store);
      if(account) await verifyWithBroker(store,account);
    } catch(error) {
      const current=store.get();
      store.transition(current.account ? store.STATES.DEGRADED : store.STATES.ERROR,{account:current.account,lastError:error.message},'backend-broker-account-error');
    } finally { busy=false; }
  }

  function schedule() {
    if(timer) clearInterval(timer);
    syncFromBackend();
    // One canonical refresh loop prevents competing account/sync requests
    // from the shell, dashboard, and trading terminal.
    timer=setInterval(syncFromBackend,30000);
  }

  window.addEventListener('algobot:account-changed',event=>{ if(window.AlgoBotBrokerState&&event.detail) window.AlgoBotBrokerState.setAccount(event.detail,'account-changed'); knownAccounts=knownAccounts.map(account=>String(account.id)===String(event.detail?.id)?event.detail:{...account,is_preferred:false}); window.AlgoBotBrokerAccounts=knownAccounts.slice(); lastAccountId=String(event.detail?.id||''); lastConnection=event.detail?.status==='active'&&event.detail?.is_connected===true; lastBalance=String(event.detail?.balance??''); });
  window.addEventListener('algobot:account-synced',event=>{ if(window.AlgoBotBrokerState&&event.detail) window.AlgoBotBrokerState.setAccount(event.detail,'account-synced'); knownAccounts=knownAccounts.map(account=>String(account.id)===String(event.detail?.id)?event.detail:account); window.AlgoBotBrokerAccounts=knownAccounts.slice(); lastAccountId=String(event.detail?.id||''); lastConnection=event.detail?.status==='active'&&event.detail?.is_connected===true; lastBalance=String(event.detail?.balance??''); });
  window.addEventListener('algobot:account-sync-error',event=>{ if(window.AlgoBotBrokerState) { const s=window.AlgoBotBrokerState.get(); window.AlgoBotBrokerState.transition(window.AlgoBotBrokerState.STATES.DEGRADED,{account:s.account,lastError:event.detail?.error?.message||'Broker synchronization failed'},'account-sync-error'); } });

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',schedule,{once:true}); else schedule();
})();
