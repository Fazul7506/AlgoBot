(() => {
  'use strict';
  if (window.__algoBotStrategyBuilder) return;
  window.__algoBotStrategyBuilder = true;
  const root = document.querySelector('[data-strategy-builder]');
  if (!root) return;
  const $ = selector => root.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const list = value => window.AlgoBotFrontendData?.list(value) || (Array.isArray(value) ? value : []);
  const select = $('[data-strategy-select]'), output = $('[data-builder-output]'), status = $('[data-builder-status]');
  const tradeButton = $('[data-trade-selected]'), saveButton = $('[data-save-strategy]'), validateButton = $('[data-validate-strategy]'), backtestButton = $('[data-backtest-strategy]'), optimizeButton = $('[data-optimize-strategy]');
  const details = $('[data-strategy-details]'), rowsRoot = $('[data-parameter-rows]'), rootUrl = '/api/strategies/';
  let strategies = [];
  const api = async (url, options = {}) => {
    if (window.AlgoBotFrontendData?.request) return window.AlgoBotFrontendData.request(url, options, 12000);
    const response = await fetch(url, {credentials:'same-origin', ...options, headers:{Accept:'application/json', ...(options.headers || {})}});
    const text = await response.text(); let data; try { data = JSON.parse(text); } catch (_) { data = {detail:text}; }
    if (!response.ok) throw new Error(data.detail || data.message || `Request failed (${response.status})`); return data;
  };
  const setStatus = (text, tone = '') => { status.textContent = text; status.dataset.tone = tone; };
  const selected = () => strategies.find(s => String(s.id) === String(select.value));

  function addParameter(name = '', value = '') {
    const empty = rowsRoot.querySelector('.parameter-empty'); empty?.remove();
    const row = document.createElement('div'); row.className = 'parameter-row';
    row.innerHTML = `<label><span>Parameter name</span><input data-param-name maxlength="80" value="${esc(name)}" placeholder="e.g. fast_period"></label><label><span>Value</span><input data-param-value value="${esc(value)}" placeholder="e.g. 20"></label><button class="btn ghost parameter-remove" type="button" data-remove-parameter>Remove</button>`;
    row.querySelector('[data-remove-parameter]').addEventListener('click', () => { row.remove(); if (!rowsRoot.children.length) rowsRoot.innerHTML = '<div class="parameter-empty">No overrides. Strategy defaults will be used.</div>'; });
    rowsRoot.appendChild(row);
    row.querySelector('[data-param-name]')?.focus();
  }

  function readParameters() {
    const parameters = {};
    rowsRoot.querySelectorAll('.parameter-row').forEach(row => {
      const key = row.querySelector('[data-param-name]')?.value.trim(); const raw = row.querySelector('[data-param-value]')?.value.trim();
      if (!key || raw === '') return;
      if (/^-?\d+(\.\d+)?$/.test(raw)) parameters[key] = Number(raw);
      else if (/^(true|false)$/i.test(raw)) parameters[key] = raw.toLowerCase() === 'true';
      else parameters[key] = raw;
    });
    return parameters;
  }

  const payload = () => ({symbol:$('[data-symbol]').value.trim().toUpperCase(), timeframe:$('[data-timeframe]').value, parameters:readParameters(), risk_profile:$('[data-risk-profile]').value, schedule:$('[data-schedule]').value});

  function resultEmpty(title, text) { output.dataset.state = ''; output.innerHTML = `<div class="result-empty"><strong>${esc(title)}</strong><span>${esc(text)}</span></div>`; }
  function resultCard(label, value) { return `<div class="result-card"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`; }
  function renderResult(data, fallbackTitle = 'Research result') {
    if (!data || typeof data !== 'object') { resultEmpty(fallbackTitle, String(data || 'No result returned.')); return; }
    const errors = list(data.errors), warnings = list(data.warnings), config = data.configuration || {};
    const strategyName = data.strategy_name || data.strategy || selected()?.name || 'Selected strategy';
    const cards = [resultCard('Strategy', strategyName), resultCard('Symbol', data.symbol || config.symbol || payload().symbol), resultCard('Timeframe', data.timeframe || config.timeframe || payload().timeframe), resultCard('Status', String(data.status || 'Ready').replaceAll('_',' '))];
    let html = `<div class="result-grid">${cards.join('')}</div>`;
    if (data.message) html += `<div class="result-section"><h3>Summary</h3><p>${esc(data.message)}</p></div>`;
    if (data.ready_for_backtest !== undefined) html += `<div class="result-section"><h3>Research readiness</h3><p>${data.ready_for_backtest ? 'Ready for backtesting.' : 'Configuration needs attention before research.'}</p></div>`;
    if (errors.length) html += `<div class="result-section"><h3>Issues</h3><ul class="result-list">${errors.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`;
    if (warnings.length) html += `<div class="result-section"><h3>Notes</h3><ul class="result-list">${warnings.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`;
    if (!errors.length && !warnings.length && !data.message) html += `<div class="result-section"><h3>Configuration</h3><p>Configuration accepted. Continue to backtesting or review the strategy in Terminal.</p></div>`;
    output.dataset.state = data.status === 'valid' || data.status === 'success' ? 'success' : errors.length ? 'error' : '';
    output.innerHTML = html;
  }

  function renderDetails(strategy) {
    if (!strategy) { details.innerHTML = '<span>Select a strategy to see its description, version and readiness.</span>'; [saveButton,validateButton,backtestButton,optimizeButton,tradeButton].forEach(b=>{if(b)b.disabled=true}); return; }
    details.innerHTML = `<strong>${esc(strategy.name)}</strong><span>${esc(strategy.description || 'No description provided.')}</span><small>${esc(strategy.category || 'Strategy')} · v${esc(strategy.version || '1.0.0')} · ${strategy.configured ? 'Configured' : 'Not configured'}</small>`;
    [saveButton,validateButton,backtestButton,optimizeButton,tradeButton].forEach(b=>{if(b)b.disabled=false});
    tradeButton.href = `/trading/?strategy=${encodeURIComponent(strategy.slug || strategy.name)}&symbol=${encodeURIComponent($('[data-symbol]').value.trim())}`;
  }

  function renderStrategies() {
    select.replaceChildren();
    if (!strategies.length) { const option=document.createElement('option'); option.value=''; option.textContent='No strategies available'; select.appendChild(option); select.disabled=true; renderDetails(null); return; }
    strategies.forEach(strategy => { const option=document.createElement('option'); option.value=strategy.id; option.textContent=`${strategy.name}${strategy.configured ? ' · configured' : ''}`; select.appendChild(option); });
    select.disabled=false;
    const requested = new URLSearchParams(location.search).get('strategy');
    const match = strategies.find(s=>String(s.slug)===requested || String(s.name)===requested || String(s.id)===requested);
    select.value=String(match?.id || strategies[0].id); renderDetails(selected());
  }

  async function load() {
    setStatus('Loading catalog…'); resultEmpty('Loading strategy catalog', 'Fetching the authoritative strategy catalog…'); [saveButton,validateButton,backtestButton,optimizeButton,tradeButton].forEach(b=>{if(b)b.disabled=true});
    try { const data=await api(`${rootUrl}available/`); strategies=list(data.strategies); renderStrategies(); setStatus(strategies.length?`${strategies.length} strategies ready`:'No strategies',strategies.length?'success':'warning'); if(strategies.length) resultEmpty('Ready for research','Select a strategy and validate its configuration to see a structured result here.'); else resultEmpty('No strategies available','The strategy catalog is empty. Refresh after the strategy service is available.'); }
    catch(error) { strategies=[]; renderStrategies(); setStatus('Unavailable','error'); resultEmpty('Strategy service unavailable',error.message || 'Request failed. Use Refresh strategies to retry.'); }
  }

  async function validate() {
    const strategy=selected(); if(!strategy)return;
    try { const body=payload(); setStatus('Validating…'); const result=await api(`${rootUrl}${encodeURIComponent(strategy.id)}/validate_config/`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); renderResult({...result,strategy_name:strategy.name,symbol:body.symbol,timeframe:body.timeframe}); setStatus(result.status==='valid'?'Configuration valid':'Validation failed',result.status==='valid'?'success':'error'); }
    catch(error) { renderResult({status:'invalid',strategy_name:strategy.name,symbol:payload().symbol,timeframe:payload().timeframe,errors:[error.message||'Validation failed.']},'Validation failed'); setStatus('Validation failed','error'); }
  }

  async function save() {
    const strategy=selected(); if(!strategy)return;
    try { const body=payload(); setStatus('Saving…'); const result=await api(`${rootUrl}${encodeURIComponent(strategy.id)}/configure/`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); renderResult({...result,strategy_name:strategy.name,symbol:body.symbol,timeframe:body.timeframe}); setStatus('Configuration saved','success'); strategy.configured=true; renderDetails(strategy); }
    catch(error) { renderResult({status:'error',strategy_name:strategy.name,errors:[error.message||'Could not save configuration.']},'Save failed'); setStatus('Save failed','error'); }
  }

  function research(destination,label) {
    const strategy=selected(); if(!strategy)return;
    try { const body=payload(); const params=new URLSearchParams({strategy:strategy.slug||strategy.name,symbol:body.symbol,timeframe:body.timeframe}); if(Object.keys(body.parameters).length) params.set('parameters',Object.entries(body.parameters).map(([k,v])=>`${k}=${v}`).join('&')); location.href=`${destination}?${params.toString()}`; }
    catch(error) { renderResult({status:'error',errors:[error.message||'Invalid configuration.']},`${label} blocked`); setStatus(`${label} blocked`,'error'); }
  }

  select.addEventListener('change',()=>renderDetails(selected()));
  $('[data-symbol]').addEventListener('input',()=>{const strategy=selected();if(strategy)renderDetails(strategy)});
  $('[data-load-strategies]').addEventListener('click',load);
  $('[data-add-parameter]').addEventListener('click',()=>addParameter());
  validateButton.addEventListener('click',validate); saveButton.addEventListener('click',save); backtestButton.addEventListener('click',()=>research('/backtesting/','Backtest')); optimizeButton.addEventListener('click',()=>research('/backtesting/','Optimization'));
  tradeButton.addEventListener('click',event=>{if(!selected())event.preventDefault()});
  load();
})();
