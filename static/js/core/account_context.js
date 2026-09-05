/* AlgoBot canonical account selector.
 * One browser selection state, persisted for navigation/refresh, reconciled with
 * the authenticated server session, and broadcast to every page module.
 */
(() => {
  'use strict';
  if (window.AlgoBotAccountContext) return;

  const STORAGE_KEY = 'algobot:selected-account-id:v1';
  const list = value => Array.isArray(value) ? value : (Array.isArray(value?.results) ? value.results : (Array.isArray(value?.accounts) ? value.accounts : []));
  let accounts = [];
  let selected = null;
  let busy = null;

  const storageGet = () => { try { return localStorage.getItem(STORAGE_KEY); } catch (_) { return null; } };
  const storageSet = id => { try { id == null ? localStorage.removeItem(STORAGE_KEY) : localStorage.setItem(STORAGE_KEY, String(id)); } catch (_) {} };
  const accountId = a => a?.id == null ? null : String(a.id);
  const canonical = () => window.AlgoBotFrontendData?.request;

  function setSelected(account, reason = 'account-selected', persist = true) {
    if (!account?.id) return null;
    selected = account;
    if (persist) storageSet(account.id);
    window.AlgoBotBrokerState?.setAccount(account, reason);
    window.dispatchEvent(new CustomEvent('algobot:account-context-changed', {detail:{account, reason}}));
    window.dispatchEvent(new CustomEvent('algobot:account-changed', {detail:account}));
    return account;
  }

  async function load(force = false) {
    if (busy && !force) return busy;
    const request = canonical();
    if (!request) return selected;
    busy = (async () => {
      const rows = list(await request('/api/brokers/accounts/', {notifyOnError:false}, 10000)).filter(a => a?.id);
      accounts = rows;
      window.AlgoBotBrokerAccounts = rows.slice();
      const storedId = storageGet();
      const target = (storedId && rows.find(a => accountId(a) === storedId))
        || rows.find(a => a.is_preferred || a.is_default || a.is_active)
        || rows[0]
        || null;
      if (!target) {
        selected = null;
        window.AlgoBotBrokerState?.reset('no-connected-broker-account');
        return null;
      }
      if (storedId && accountId(target) === storedId) {
        try {
          const result = await request(`/api/brokers/accounts/${encodeURIComponent(target.id)}/select/`, {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({account_type: String(target.account_type || target.credentials?.account_type || '').toLowerCase()}) ,
            notifyOnError:false
          }, 8000);
          const confirmed = result?.active_account || result?.account;
          if (confirmed?.id) {
            accounts = accounts.map(a => accountId(a) === accountId(confirmed) ? confirmed : {...a, is_preferred:false, is_active:false});
            window.AlgoBotBrokerAccounts = accounts.slice();
            setSelected(confirmed, 'account-context-hydrated', true);
            return confirmed;
          }
        } catch (_) {
          storageSet(null);
        }
      }
      setSelected(target, 'account-context-hydrated', true);
      return target;
    })().finally(() => { busy = null; });
    return busy;
  }

  async function selectAccount(id) {
    const target = accounts.find(a => accountId(a) === String(id));
    if (!target) throw new Error('The selected broker account is no longer available. Refresh the account list.');
    if (target.switch_enabled === false) throw new Error('Broker account switching is disabled by platform configuration.');
    const request = canonical();
    if (!request) throw new Error('The account API is not ready.');
    const requestedType = String(target.account_type || target.credentials?.account_type || '').toLowerCase();
    if (!['demo','real'].includes(requestedType)) throw new Error('Synchronize the broker account before switching to it.');
    if (busy) await busy.catch(() => {});
    const result = await request(`/api/brokers/accounts/${encodeURIComponent(target.id)}/select/`, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({account_type:requestedType})
    }, 8000);
    const confirmed = result?.active_account || result?.account;
    if (!confirmed?.id || accountId(confirmed) !== accountId(target)) throw new Error('Broker did not confirm the selected account.');
    accounts = accounts.map(a => accountId(a) === accountId(confirmed) ? confirmed : {...a, is_preferred:false, is_active:false});
    window.AlgoBotBrokerAccounts = accounts.slice();
    setSelected(confirmed, 'account-switch', true);
    return confirmed;
  }

  function getSelected() { return selected || window.AlgoBotBrokerState?.get?.().account || null; }
  function getSelectedId() { return accountId(getSelected()) || storageGet(); }
  function getAccounts() { return accounts.slice(); }

  window.AlgoBotAccountContext = Object.freeze({load, refresh:() => load(true), selectAccount, getSelected, getSelectedId, getAccounts});

  window.addEventListener('algobot:backend-accounts-loaded', event => {
    const rows = list(event.detail).filter(a => a?.id);
    if (rows.length) accounts = rows;
    const id = storageGet();
    if (id) {
      const target = accounts.find(a => accountId(a) === id);
      if (target) setSelected(target, 'backend-accounts-rehydrated', false);
    }
  });
  window.addEventListener('algobot:account-synced', event => {
    if (!event.detail?.id) return;
    const id = accountId(event.detail);
    accounts = accounts.map(a => accountId(a) === id ? event.detail : a);
    if (getSelectedId() === id) setSelected(event.detail, 'account-synced', true);
  });

  const boot = () => {
    if (document.body.dataset.authenticated === 'true') load().catch(error => {
      window.dispatchEvent(new CustomEvent('algobot:account-context-error', {detail:error}));
    });
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true}); else boot();
})();
