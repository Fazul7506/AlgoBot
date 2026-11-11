/* Regression: browser hydration must never promote an unselected OAuth row. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function createHarness(rows, active) {
  const listeners = new Map();
  const dispatched = [];
  const window = {
    AlgoBotFrontendData: {
      request: async (url) => {
        if (url === '/api/brokers/accounts/') return {results: rows};
        if (url === '/api/brokers/accounts/active/') return active;
        throw new Error(`Unexpected request ${url}`);
      }
    },
    AlgoBotBrokerState: {reset: reason => dispatched.push(['reset', reason]), setAccount: account => dispatched.push(['set', account]), get: () => ({account: {id: 99, account_type: 'demo'}})},
    addEventListener: (name, fn) => listeners.set(name, fn),
    dispatchEvent: event => { dispatched.push([event.type, event.detail]); return true; }
  };
  const document = {
    readyState: 'complete', body: {dataset: {authenticated: 'false'}},
    addEventListener() {},
  };
  class CustomEvent { constructor(type, options = {}) { this.type = type; this.detail = options.detail; } }
  const localStorage = {values: new Map([['algobot:selected-account-id:v1','9']]), setItem(k,v){this.values.set(k,v)}, removeItem(k){this.values.delete(k)}};
  const context = {window, document, localStorage, CustomEvent, console};
  vm.runInNewContext(fs.readFileSync(require.resolve('./account_context.js'), 'utf8'), context);
  return {window, localStorage};
}

(async () => {
  const credentialReady = {id: 9, status: 'active', credential_status: 'ready', is_connected: true, account_type: 'real'};
  const noSelection = createHarness([credentialReady], {active_account: null, active_account_id: null});
  await noSelection.window.AlgoBotAccountContext.load();
  assert.equal(noSelection.window.AlgoBotAccountContext.getSelected(), null);
  assert.equal(noSelection.window.AlgoBotAccountContext.getSelectedId(), null);
  assert.equal(noSelection.window.AlgoBotAccountContext.getSelected(), null);
  assert.equal(noSelection.localStorage.values.has('algobot:selected-account-id:v1'), false);

  const serverSelected = {...credentialReady, is_active: true, is_connected: true};
  const confirmed = createHarness([serverSelected], {active_account: serverSelected, active_account_id: 9});
  await confirmed.window.AlgoBotAccountContext.load();
  assert.equal(confirmed.window.AlgoBotAccountContext.getSelectedId(), '9');
  console.log('Account context server-authority regression tests passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
