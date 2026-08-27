/* Live connected-broker market capability bridge. */
(() => {
  'use strict';
  if (window.__algoBotBrokerNativeMarket) return;
  window.__algoBotBrokerNativeMarket = true;

  const $ = (s, r = document) => r.querySelector(s);
  const list = v => window.AlgoBotFrontendData?.list(v) || [];
  const esc = v => String(v ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[c]));
  const api = (url, options = {}, timeout = 12000) => window.AlgoBotFrontendData.request(url, options, timeout);
  const directionFor = type => {
    const t = String(type || '').toUpperCase();
    if (/PUT|FALL|LOWER|MULTDOWN|DIGITUNDER|NOTOUCH|PUTE|TURBOSSHORT|RUNLOW|EXPIRYMISS/.test(t)) return 'SELL';
    return 'BUY';
  };
  let contracts = [];
  let capabilitiesRequest = 0;

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
    contracts = list(payload?.contracts).filter(c => c?.contract_type);
    const select = $('[data-contract-type]');
    const typeLabel = $('[data-broker-trade-type]');
    const status = $('[data-contract-status]');
    if (!select) return;
    if (!contracts.length) {
      select.innerHTML = '<option value="">No broker contracts available</option>';
      select.disabled = true;
      if (typeLabel) typeLabel.textContent = 'Unavailable';
      if (status) status.textContent = 'Deriv reports no contracts for this instrument';
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
    if (status) status.textContent = `${contracts.length} broker-supported contract types`;
  }

  function applyContract(type) {
    const selected = contracts.find(c => String(c.contract_type) === String(type));
    if (!selected) return;
    const direction = directionFor(selected.contract_type);
    const button = document.querySelector(`[data-direction="${direction}"]`);
    if (button) button.click();
    const category = selected.contract_category || 'Broker contract';
    const label = $('[data-broker-trade-type]'); if (label) label.textContent = category;
    window.__algobotAiOrderContext = {
      ...(window.__algobotAiOrderContext || {}),
      broker_source: 'connected_broker',
      contract_type: selected.contract_type,
      contract_category: selected.contract_category || '',
      expiry_type: selected.expiry_type || '',
      underlying_symbol: selected.underlying_symbol || $('#symbol')?.value || '',
      sentiment: selected.sentiment || '',
    };
  }

  async function loadCapabilities(symbol) {
    const requestId = ++capabilitiesRequest;
    const select = $('[data-contract-type]');
    if (!select || !symbol) return;
    select.disabled = true;
    select.innerHTML = '<option value="">Loading broker contracts…</option>';
    try {
      const payload = await api(`/api/market/broker-capabilities/?symbol=${encodeURIComponent(symbol)}`, {}, 12000);
      if (requestId !== capabilitiesRequest) return;
      renderContracts(payload);
    } catch (error) {
      if (requestId !== capabilitiesRequest) return;
      select.innerHTML = `<option value="">Broker contracts unavailable</option>`;
      if ($('[data-contract-status]')) $('[data-contract-status]').textContent = error.message || 'Broker capability request failed';
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

  function boot() {
    if (!$('.terminal-page')) return;
    installRequestBridge();
    setHiddenCompatibilityFields();
    const symbol = $('#symbol');
    const contract = $('[data-contract-type]');
    symbol?.addEventListener('change', () => loadCapabilities(symbol.value));
    contract?.addEventListener('change', () => applyContract(contract.value));
    if (symbol?.value) loadCapabilities(symbol.value);
    // trading_terminal loads its broker account and catalogue asynchronously;
    // retry briefly so the capability selector follows the final broker symbol.
    let attempts = 0;
    const timer = setInterval(() => {
      attempts += 1;
      installRequestBridge();
      setHiddenCompatibilityFields();
      if (symbol?.value && (!contracts.length || contracts[0]?.underlying_symbol !== symbol.value)) loadCapabilities(symbol.value);
      if (attempts >= 10) clearInterval(timer);
    }, 700);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true}); else boot();
})();
