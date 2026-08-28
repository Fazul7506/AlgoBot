(() => {
  'use strict';
  if (window.__algoBotStrategyBuilder) return;
  window.__algoBotStrategyBuilder = true;

  const root = document.querySelector('[data-strategy-builder]');
  if (!root) return;

  const $ = selector => root.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const list = value => window.AlgoBotFrontendData?.list(value) || (Array.isArray(value) ? value : []);
  const select = $('[data-strategy-select]');
  const output = $('[data-builder-output]');
  const status = $('[data-builder-status]');
  const tradeButton = $('[data-trade-selected]');
  const saveButton = $('[data-save-strategy]');
  const validateButton = $('[data-validate-strategy]');
  const backtestButton = $('[data-backtest-strategy]');
  const optimizeButton = $('[data-optimize-strategy]');
  const details = $('[data-strategy-details]');
  const rootUrl = '/api/strategies/';
  let strategies = [];

  const api = async (url, options = {}) => {
    if (window.AlgoBotFrontendData?.request) return window.AlgoBotFrontendData.request(url, options, 12000);
    const response = await fetch(url, {credentials:'same-origin', ...options, headers:{Accept:'application/json', ...(options.headers || {})}});
    const text = await response.text();
    let data;
    try { data = JSON.parse(text); } catch (_) { data = {detail: text}; }
    if (!response.ok) throw new Error(data.detail || data.message || `Request failed (${response.status})`);
    return data;
  };

  const setStatus = (text, tone = '') => {
    status.textContent = text;
    status.dataset.tone = tone;
  };

  const selected = () => strategies.find(s => String(s.id) === String(select.value));
  const payload = () => {
    let parameters = {};
    try { parameters = JSON.parse($('[data-param-grid]').value || '{}'); }
    catch (_) { throw new Error('Parameter grid must contain valid JSON.'); }
    return {
      symbol: $('[data-symbol]').value.trim().toUpperCase(),
      timeframe: $('[data-timeframe]').value,
      parameters,
      risk_profile: $('[data-risk-profile]').value,
      schedule: $('[data-schedule]').value,
    };
  };

  function renderDetails(strategy) {
    if (!strategy) {
      details.innerHTML = '<span>Select a strategy to see its description, version and readiness.</span>';
      [saveButton, validateButton, backtestButton, optimizeButton, tradeButton].forEach(button => { if (button) button.disabled = true; });
      return;
    }
    details.innerHTML = `<strong>${esc(strategy.name)}</strong><span>${esc(strategy.description || 'No description provided.')}</span><small>${esc(strategy.category || 'Strategy')} · v${esc(strategy.version || '1.0.0')} · ${strategy.configured ? 'Configured' : 'Not configured'}</small>`;
    [saveButton, validateButton, backtestButton, optimizeButton, tradeButton].forEach(button => { if (button) button.disabled = false; });
    tradeButton.href = `/trading/?strategy=${encodeURIComponent(strategy.slug || strategy.name)}&symbol=${encodeURIComponent($('[data-symbol]').value.trim())}`;
  }

  function renderStrategies() {
    select.replaceChildren();
    if (!strategies.length) {
      const option = document.createElement('option'); option.value = ''; option.textContent = 'No strategies available'; select.appendChild(option);
      renderDetails(null);
      return;
    }
    strategies.forEach(strategy => {
      const option = document.createElement('option');
      option.value = strategy.id;
      option.textContent = `${strategy.name}${strategy.configured ? ' · configured' : ''}`;
      select.appendChild(option);
    });
    const requested = new URLSearchParams(location.search).get('strategy');
    const requestedMatch = strategies.find(s => String(s.slug) === requested || String(s.name) === requested || String(s.id) === requested);
    select.value = String(requestedMatch?.id || strategies[0].id);
    renderDetails(selected());
  }

  async function load() {
    setStatus('Loading catalog…');
    output.textContent = 'Loading the authoritative strategy catalog…';
    [saveButton, validateButton, backtestButton, optimizeButton, tradeButton].forEach(button => { if (button) button.disabled = true; });
    try {
      const data = await api(`${rootUrl}available/`);
      strategies = list(data.strategies);
      renderStrategies();
      setStatus(strategies.length ? `${strategies.length} strategies ready` : 'No strategies', strategies.length ? 'success' : 'warning');
      output.textContent = strategies.length ? 'Select a strategy, configure its research parameters, validate the configuration, then backtest or trade it.' : 'The strategy catalog is empty. Refresh after the strategy service is available.';
    } catch (error) {
      strategies = [];
      renderStrategies();
      setStatus('Unavailable', 'error');
      output.textContent = `Strategy service unavailable: ${error.message || 'request failed'}\n\nUse Refresh strategies to retry.`;
    }
  }

  async function validate() {
    const strategy = selected(); if (!strategy) return;
    try {
      const body = payload();
      setStatus('Validating…');
      const result = await api(`${rootUrl}${encodeURIComponent(strategy.id)}/validate_config/`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
      output.textContent = JSON.stringify(result, null, 2);
      setStatus(result.status === 'valid' ? 'Configuration valid' : 'Validation failed', result.status === 'valid' ? 'success' : 'error');
    } catch (error) {
      output.textContent = error.message || 'Validation failed.';
      setStatus('Validation failed', 'error');
    }
  }

  async function save() {
    const strategy = selected(); if (!strategy) return;
    try {
      const body = payload();
      setStatus('Saving…');
      const result = await api(`${rootUrl}${encodeURIComponent(strategy.id)}/configure/`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
      output.textContent = JSON.stringify(result, null, 2);
      setStatus('Configuration saved', 'success');
      strategy.configured = true;
      renderDetails(strategy);
    } catch (error) {
      output.textContent = error.message || 'Could not save configuration.';
      setStatus('Save failed', 'error');
    }
  }

  function research(destination, label) {
    const strategy = selected(); if (!strategy) return;
    try {
      const body = payload();
      const params = new URLSearchParams({strategy: strategy.slug || strategy.name, symbol: body.symbol, timeframe: body.timeframe});
      if (body.parameters && Object.keys(body.parameters).length) params.set('parameters', JSON.stringify(body.parameters));
      location.href = `${destination}?${params.toString()}`;
    } catch (error) {
      output.textContent = error.message || 'Invalid configuration.';
      setStatus(`${label} blocked`, 'error');
    }
  }

  select.addEventListener('change', () => renderDetails(selected()));
  $('[data-symbol]').addEventListener('input', () => { const strategy = selected(); if (strategy) renderDetails(strategy); });
  $('[data-load-strategies]').addEventListener('click', load);
  validateButton.addEventListener('click', validate);
  saveButton.addEventListener('click', save);
  backtestButton.addEventListener('click', () => research('/backtesting/', 'Backtest'));
  optimizeButton.addEventListener('click', () => research('/backtesting/', 'Optimization'));
  tradeButton.addEventListener('click', event => {
    const strategy = selected();
    if (!strategy) event.preventDefault();
  });

  load();
})();
