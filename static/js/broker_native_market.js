/* Live connected-broker market capability bridge. */
(() => {
  'use strict';
  if (window.__algoBotBrokerNativeMarket) return;
  window.__algoBotBrokerNativeMarket = true;

  const $ = (s, r = document) => r.querySelector(s);
  const list = v => window.AlgoBotFrontendData?.list(v) || [];
  const esc = v => String(v ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[c]));
  const api = (url, options = {}, timeout = 12000) => window.AlgoBotFrontendData?.request?.(url, options, timeout);
  const PUBLIC_WS = 'wss://api.derivws.com/trading/v1/options/ws/public';
  let contracts = [];
  let capabilitiesRequest = 0;
  let socketRequestId = 1000;

  const directionFor = type => {
    const t = String(type || '').toUpperCase();
    if (/PUT|FALL|LOWER|MULTDOWN|DIGITUNDER|NOTOUCH|TURBOSSHORT|RUNLOW|EXPIRYMISS/.test(t)) return 'SELL';
    return 'BUY';
  };

  function setStatus(message) {
    $('[data-contract-status]')?.replaceChildren(document.createTextNode(String(message || '')));
  }

  function setHiddenCompatibilityFields() {
    const form = $('[data-order-form]');
    if (!form) return;
    if (!form.querySelector('input[name="order_type"]')) {
      const input = document.createElement('input'); input.type = 'hidden'; input.name = 'order_type'; input.value = 'market'; form.prepend(input);
    }
    if (!form.querySelector('input[name="strategy"]')) {
      const input = document.createElement('input'); input.type = 'hidden'; input.name = 'strategy'; input.value = ''; form.appendChild(input);
    }
  }

  function renderContracts(payload) {
    const raw = Array.isArray(payload) ? payload : (payload?.contracts || payload?.available || payload?.contracts_for?.available || []);
    contracts = raw.filter(c => c && c.contract_type).map(c => ({
      ...c,
      contract_type: String(c.contract_type),
      contract_category: String(c.contract_category || ''),
      expiry_type: String(c.expiry_type || ''),
      underlying_symbol: String(c.underlying_symbol || $('#symbol')?.value || ''),
    }));

    const select = $('[data-contract-type]');
    const typeLabel = $('[data-broker-trade-type]');
    if (!select) return;

    if (!contracts.length) {
      select.innerHTML = '<option value="">No broker contracts available</option>';
      select.disabled = true;
      if (typeLabel) typeLabel.textContent = 'Unavailable';
      setStatus('Deriv reports no contracts for this instrument');
      return;
    }

    const previous = select.value;
    select.innerHTML = contracts.map(c => {
      const label = c.contract_type + (c.contract_category ? ` · ${c.contract_category}` : '');
      return `<option value="${esc(c.contract_type)}">${esc(label)}</option>`;
    }).join('');
    select.disabled = false;
    select.value = contracts.some(c => c.contract_type === previous) ? previous : contracts[0].contract_type;
    applyContract(select.value);
    setStatus(`${contracts.length} broker-supported contract type${contracts.length === 1 ? '' : 's'}`);
  }

  function applyContract(type) {
    const selected = contracts.find(c => String(c.contract_type) === String(type));
    if (!selected) return;

    const direction = directionFor(selected.contract_type);
    const button = document.querySelector(`[data-direction="${direction}"]`);
    if (button) button.click();

    const category = selected.contract_category || selected.contract_type || 'Broker contract';
    const label = $('[data-broker-trade-type]');
    if (label) label.textContent = category;

    window.__algobotSelectedBrokerContract = selected;
    window.__algobotAiOrderContext = {
      ...(window.__algobotAiOrderContext || {}),
      broker_source: 'connected_broker',
      contract_type: selected.contract_type,
      contract_category: selected.contract_category || '',
      expiry_type: selected.expiry_type || '',
      underlying_symbol: selected.underlying_symbol || $('#symbol')?.value || '',
      sentiment: selected.sentiment || '',
      market: selected.market || '',
      submarket: selected.submarket || '',
    };

    window.dispatchEvent(new CustomEvent('algobot:broker-contract-selected', {detail: selected}));
  }

  function directDerivContracts(symbol, timeout = 12000) {
    return new Promise((resolve, reject) => {
      if (!symbol) return reject(new Error('Broker instrument is required'));
      let ws;
      let timer;
      const reqId = ++socketRequestId;
      const finish = (error, data) => {
        clearTimeout(timer);
        try { ws?.close(); } catch (_) {}
        error ? reject(error) : resolve(data);
      };
      try { ws = new WebSocket(PUBLIC_WS); }
      catch (error) { finish(error); return; }
      timer = setTimeout(() => finish(new Error('Deriv contract request timed out')), timeout);
      ws.onopen = () => ws.send(JSON.stringify({contracts_for: symbol, req_id: reqId}));
      ws.onmessage = event => {
        try {
          const data = JSON.parse(event.data);
          if (data.error) return finish(new Error(data.error.message || 'Deriv rejected contract request'));
          if (Number(data.req_id) === reqId || data.msg_type === 'contracts_for') finish(null, data);
        } catch (error) { finish(error); }
      };
      ws.onerror = () => finish(new Error('Deriv public contract connection failed'));
    });
  }

  async function loadCapabilities(symbol) {
    const requestId = ++capabilitiesRequest;
    const select = $('[data-contract-type]');
    if (!select || !symbol) return;

    select.disabled = true;
    select.innerHTML = '<option value="">Loading broker contracts…</option>';
    if ($('[data-broker-trade-type]')) $('[data-broker-trade-type]').textContent = 'Loading';
    setStatus('Connecting to Deriv contract catalogue…');

    try {
      // Primary source is the same public Deriv WebSocket used by the chart.
      // This removes Render/API latency from the broker contract selector.
      const payload = await directDerivContracts(symbol);
      if (requestId !== capabilitiesRequest) return;
      renderContracts(payload);
      return;
    } catch (directError) {
      // Keep the existing backend route as a resilience fallback. It is still
      // broker-authoritative because broker_native.capabilities calls Deriv.
      try {
        const payload = await api(`/api/market/broker-capabilities/?symbol=${encodeURIComponent(symbol)}`, {}, 12000);
        if (requestId !== capabilitiesRequest) return;
        renderContracts(payload);
        return;
      } catch (backendError) {
        if (requestId !== capabilitiesRequest) return;
        select.innerHTML = '<option value="">Broker contracts unavailable</option>';
        select.disabled = true;
        if ($('[data-broker-trade-type]')) $('[data-broker-trade-type]').textContent = 'Unavailable';
        setStatus(backendError?.message || directError?.message || 'Broker capability request failed');
      }
    }
  }

  function installRequestBridge() {
    const frontend = window.AlgoBotFrontendData;
    if (!frontend?.request || frontend.__brokerNativeBridge) return;
    const original = frontend.request.bind(frontend);
    frontend.request = (url, options = {}, timeout = 10000) => {
      const target = String(url || '');
      if (target === '/api/market/catalogue/' || target === '/api/markets/catalogue/') {
        return original('/api/market/broker-catalogue/', options, timeout);
      }
      if (target.startsWith('/api/market/chart/capabilities/')) {
        const symbol = new URLSearchParams(target.split('?')[1] || '').get('symbol') || $('#symbol')?.value;
        return original(`/api/market/broker-capabilities/?symbol=${encodeURIComponent(symbol || '')}`, options, timeout);
      }
      return original(url, options, timeout);
    };
    frontend.__brokerNativeBridge = true;
  }

  function currentSymbol() { return String($('#symbol')?.value || '').trim(); }

  function triggerCurrentSymbol() {
    const symbol = currentSymbol();
    if (symbol) loadCapabilities(symbol);
  }

  function boot() {
    if (!$('.terminal-page')) return;
    installRequestBridge();
    setHiddenCompatibilityFields();

    const symbol = $('#symbol');
    const contract = $('[data-contract-type]');
    symbol?.addEventListener('change', () => loadCapabilities(symbol.value));
    contract?.addEventListener('change', () => applyContract(contract.value));

    // Trading terminal populates the broker symbol list asynchronously.
    // Listen for its completion and also observe value changes so contract
    // loading cannot remain stuck on the initial loading placeholder.
    window.addEventListener('algobot:broker-symbols-loaded', triggerCurrentSymbol);
    window.addEventListener('algobot:market-symbol-changed', triggerCurrentSymbol);
    window.addEventListener('algobot:account-synced', triggerCurrentSymbol);

    let last = '';
    const timer = setInterval(() => {
      installRequestBridge();
      setHiddenCompatibilityFields();
      const value = currentSymbol();
      if (value && value !== last) {
        last = value;
        loadCapabilities(value);
      }
    }, 500);

    setTimeout(() => clearInterval(timer), 30000);
    if (currentSymbol()) triggerCurrentSymbol();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true});
  else boot();
})();
