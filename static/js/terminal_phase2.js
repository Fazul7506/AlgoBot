/* Production Trading Terminal: authoritative preview, execution state, chart controls, and mobile-safe UX. */
(function () {
  'use strict';
  if (window.__algoBotTerminalPhase2) return;
  window.__algoBotTerminalPhase2 = true;

  function $(selector, root) { return (root || document).querySelector(selector); }
  function $$(selector, root) { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); }
  function api(url, options, timeout) {
    if (!window.AlgoBotFrontendData || !window.AlgoBotFrontendData.request) return Promise.reject(new Error('Frontend API transport is unavailable'));
    return window.AlgoBotFrontendData.request(url, options || {}, timeout || 10000);
  }
  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (char) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char];
    });
  }
  var previewFingerprint = '';
  var previewData = null;
  var executionPoll = null;
  var chartMode = 'ticks';

  function activeAccount() {
    if (window.AlgoBotAccountContext && window.AlgoBotAccountContext.getSelected) {
      var selected = window.AlgoBotAccountContext.getSelected();
      if (selected) return selected;
    }
    if (window.AlgoBotBrokerState && window.AlgoBotBrokerState.get) {
      var state = window.AlgoBotBrokerState.get();
      return state && state.account ? state.account : null;
    }
    return null;
  }
  function orderContext() {
    var account = activeAccount();
    var activeDirection = $('[data-direction].active');
    return {
      accountId: account && account.id != null ? account.id : '',
      symbol: $('#symbol') ? $('#symbol').value : '',
      direction: activeDirection && activeDirection.dataset.direction ? activeDirection.dataset.direction : 'BUY',
      stake: $('[name="stake"]') ? $('[name="stake"]').value : '1',
      orderType: $('[name="order_type"]') ? $('[name="order_type"]').value : 'market',
      strategy: $('[name="strategy"]') ? $('[name="strategy"]').value : '',
      contractType: $('[data-contract-type]') ? $('[data-contract-type]').value : ''
    };
  }
  function fingerprint(context) { return JSON.stringify(context); }
  function setPreview(html, state) {
    var target = $('[data-order-preview]');
    if (!target) return;
    target.hidden = false;
    target.dataset.state = state || 'info';
    target.innerHTML = html;
  }
  function invalidatePreview(reason) {
    previewFingerprint = '';
    previewData = null;
    var target = $('[data-order-preview]');
    if (target && !target.hidden) setPreview('<strong>PREVIEW REQUIRED</strong><div>' + esc(reason || 'Order context changed. Run preview again before submitting.') + '</div>', 'validation');
    var submit = $('.execute-btn');
    if (submit) submit.dataset.previewRequired = 'true';
  }
  function authoritativeAccount() {
    var selected = activeAccount();
    if (selected) return Promise.resolve(selected);
    if (!window.AlgoBotAccountContext || !window.AlgoBotAccountContext.load) return Promise.resolve(null);
    return window.AlgoBotAccountContext.load().then(function () { return activeAccount(); }).catch(function () { return null; });
  }
  function preview() {
    var context = orderContext();
    var target = $('[data-order-preview]');
    if (!target) return Promise.resolve(false);
    setPreview('<strong>CHECKING</strong><div>Running authoritative broker, market, environment and risk gates…</div>', 'pending');
    return authoritativeAccount().then(function (account) {
      if (!account || String(account.id) !== String(context.accountId)) {
        invalidatePreview('The selected account is not the authoritative active broker account. Refresh the account selector and try again.');
        return false;
      }
      if (!context.symbol || !context.contractType) {
        setPreview('<strong>REJECTED</strong><div>Select a broker instrument and wait for its supported contract list.</div>', 'validation');
        return false;
      }
      var fp = fingerprint(context);
      return api('/api/orders/preview/', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          broker_account: Number(context.accountId),
          symbol: context.symbol,
          direction: context.direction.toLowerCase(),
          order_type: context.orderType,
          stake: context.stake,
          strategy: context.strategy,
          validation_context: {
            broker_source: 'connected_broker',
            contract_type: context.contractType,
            underlying_symbol: context.symbol,
            authoritative_account_id: context.accountId
          }
        })
      }, 15000).then(function (data) {
        previewFingerprint = fp;
        previewData = data;
        var ready = data && data.status === 'ready';
        var gates = data && data.gates ? data.gates : {};
        var accountData = data && data.account ? data.account : {};
        var market = data && data.market ? data.market : {};
        setPreview('<strong>' + (ready ? 'READY TO SUBMIT' : 'REJECTED') + '</strong>' +
          '<div>' + esc(accountData.broker || 'Broker') + ' · ' + esc(accountData.account_id || account.account_id || '') + ' · ' + esc(accountData.environment || '') + '</div>' +
          '<div>Contract ' + esc(context.contractType) + ' · ' + esc(context.symbol) + ' · ' + esc(context.direction) + '</div>' +
          '<div>Bid ' + esc(market.bid == null ? '—' : market.bid) + ' · Ask ' + esc(market.ask == null ? '—' : market.ask) + ' · Spread ' + esc(market.spread == null ? '—' : market.spread) + '</div>' +
          '<div>Fresh data: ' + (gates.fresh_market_data ? 'YES' : 'NO') + ' · Environment: ' + (gates.environment_verified ? 'VERIFIED' : 'FAILED') + ' · Risk: ' + (gates.risk_verified ? 'VERIFIED' : 'NOT VERIFIED') + ' · AI: ' + (gates.ai_verified ? 'VERIFIED' : 'NOT REQUIRED') + '</div>' +
          (data && data.message ? '<div>' + esc(data.message) + '</div>' : ''), ready ? 'success' : 'error');
        var submit = $('.execute-btn');
        if (submit) submit.dataset.previewRequired = ready ? 'false' : 'true';
        return ready;
      }).catch(function (error) {
        previewFingerprint = '';
        previewData = null;
        var submit = $('.execute-btn');
        if (submit) submit.dataset.previewRequired = 'true';
        setPreview('<strong>PREVIEW REJECTED</strong><div>' + esc(error && error.message ? error.message : 'Authoritative pre-trade validation failed.') + '</div>', 'error');
        return false;
      });
    });
  }
  function reconcileOrder(orderId, brokerReference) {
    if (!orderId && !brokerReference) return;
    if (executionPoll) window.clearInterval(executionPoll);
    var attempts = 0;
    function poll() {
      attempts += 1;
      api('/api/orders/?limit=20', {}, 9000).then(function (rows) {
        var items = window.AlgoBotFrontendData && window.AlgoBotFrontendData.list ? window.AlgoBotFrontendData.list(rows) : (Array.isArray(rows) ? rows : []);
        var match = items.find(function (order) { return String(order.id) === String(orderId) || (brokerReference && String(order.broker_reference) === String(brokerReference)); });
        if (!match) return;
        var status = String(match.status || '').toLowerCase();
        var terminal = ['filled','open','executed','completed','won','lost','rejected','failed','cancelled','expired'].some(function (value) { return status.indexOf(value) >= 0; });
        var result = $('[data-order-result]');
        if (result) {
          result.dataset.state = terminal && ['rejected','failed','cancelled'].every(function (value) { return status.indexOf(value) < 0; }) ? 'success' : (terminal ? 'error' : 'pending');
          result.textContent = 'Order ' + (match.broker_reference || match.id || '') + ': ' + (match.status || 'pending') + (terminal ? '' : ' · broker confirmation pending');
          result.hidden = false;
        }
        if (terminal || attempts >= 12) {
          window.clearInterval(executionPoll);
          executionPoll = null;
          window.dispatchEvent(new CustomEvent('algobot:terminal-order-reconciled', {detail: match}));
        }
      }).catch(function () {
        if (attempts >= 12) { window.clearInterval(executionPoll); executionPoll = null; }
      });
    }
    poll();
    executionPoll = window.setInterval(poll, 2500);
  }
  function guardSubmit(event) {
    var context = orderContext();
    if (previewFingerprint !== fingerprint(context) || !previewData || previewData.status !== 'ready') {
      event.preventDefault();
      preview().then(function () {
        var result = $('[data-order-result]');
        if (result) { result.hidden = false; result.dataset.state = 'validation'; result.textContent = 'Preview required for the current account, symbol, contract and stake. Review the result, then place the order again.'; }
      });
      return false;
    }
    return true;
  }
  function chartControls() {
    var terminal = $('.terminal-page');
    if (!terminal) return;
    $$('[data-chart-mode]').forEach(function (button) {
      if (button.dataset.phase2Bound) return;
      button.dataset.phase2Bound = '1';
      button.addEventListener('click', function () {
        chartMode = button.dataset.chartMode || 'ticks';
        $$('[data-chart-mode]').forEach(function (item) { item.classList.toggle('active', item === button); });
        window.dispatchEvent(new CustomEvent('algobot:terminal-chart-mode', {detail: {mode: chartMode}}));
      });
    });
    $$('[data-chart-action]').forEach(function (button) {
      if (button.dataset.phase2Bound) return;
      button.dataset.phase2Bound = '1';
      button.addEventListener('click', function () {
        var action = button.dataset.chartAction;
        var chartCanvas = $('[data-candle-chart]');
        var chart = chartCanvas ? chartCanvas.closest('.terminal-chart') : null;
        if (action === 'fit') window.dispatchEvent(new CustomEvent('algobot:terminal-chart-fit'));
        else if (action === 'live') window.dispatchEvent(new CustomEvent('algobot:terminal-chart-live'));
        else if (action === 'fullscreen' && chart && chart.requestFullscreen) chart.requestFullscreen();
        else if (action === 'screenshot' && chartCanvas && chartCanvas.toDataURL) {
          var link = document.createElement('a');
          link.download = 'algobot-' + (($('#symbol') && $('#symbol').value) || 'market').replace(/[^a-z0-9_-]/gi, '_') + '-snapshot.png';
          link.href = chartCanvas.toDataURL('image/png');
          link.click();
        } else if (action === 'export') window.dispatchEvent(new CustomEvent('algobot:terminal-chart-export', {detail: {symbol: ($('#symbol') && $('#symbol').value) || '', mode: chartMode}}));
      });
    });
  }
  function bindContext() {
    var terminal = $('.terminal-page');
    if (!terminal) return;
    var ticket = $('.order-ticket');
    if (!ticket) return;
    var previewButton = $('[data-order-preview-button]', ticket);
    if (previewButton && !previewButton.dataset.bound) { previewButton.dataset.bound = '1'; previewButton.addEventListener('click', preview); }
    var form = $('[data-order-form]', ticket);
    if (form && !form.dataset.phase2Bound) { form.dataset.phase2Bound = '1'; form.addEventListener('submit', guardSubmit, true); }
    ['#account','#symbol','[data-contract-type]','[name="stake"]','[name="strategy"]'].forEach(function (selector) {
      var node = $(selector);
      if (node && !node.dataset.previewInvalidator) {
        node.dataset.previewInvalidator = '1';
        node.addEventListener('change', function () { invalidatePreview('Order context changed. Run a new preview.'); });
        node.addEventListener('input', function () { invalidatePreview('Order context changed. Run a new preview.'); });
      }
    });
    $$('[data-direction]').forEach(function (node) {
      if (!node.dataset.previewInvalidator) { node.dataset.previewInvalidator = '1'; node.addEventListener('click', function () { invalidatePreview('Order direction changed. Run a new preview.'); }); }
    });
    window.addEventListener('algobot:account-changed', function () { invalidatePreview('Active account changed. Run a new preview for the new account.'); });
    window.addEventListener('algobot:market-data-state', function (event) { if (!event.detail || event.detail.state !== 'live') invalidatePreview('Live broker market data is not currently verified.'); });
    window.addEventListener('algobot:order-created', function (event) { var detail = event.detail || {}; reconcileOrder(detail.id, detail.broker_reference); });
    chartControls();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bindContext, {once: true}); else bindContext();
})();
