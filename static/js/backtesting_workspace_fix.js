(() => {
'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const form = $('[data-backtest-form]');
const table = $('[data-backtest-table]');
if (!form || !table) return;

const strategy = form.elements.strategy_id;
const symbol = form.elements.symbol;
const timeframe = form.elements.timeframe;
const DEFAULT_TIMEFRAMES = ['tick','1s','5s','15s','30s','1m','2m','5m','10m','15m','30m','1h','4h','1d'];
let rows = [];
let marketMeta = {};
let catalogueTimeframes = [];
let strategyCatalog = [];

const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;'
}[char]));

const csrf = () => decodeURIComponent((document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/) || [])[1] || '');

async function request(url, options = {}, timeout = 15000) {
  if (window.AlgoBotFrontendData?.request) return window.AlgoBotFrontendData.request(url, options, timeout);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, {
      credentials: 'same-origin',
      headers: {Accept: 'application/json', ...(options.headers || {})},
      signal: controller.signal,
      ...options,
    });
    const text = await response.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch { data = {detail: text}; }
    if (!response.ok) {
      const detail = data.detail || data.message || Object.values(data).flat().join(' ') || `Request failed (${response.status})`;
      throw new Error(detail);
    }
    return data;
  } finally {
    clearTimeout(timer);
  }
}

function list(value, keys = []) {
  if (Array.isArray(value)) return value;
  for (const key of keys) if (Array.isArray(value?.[key])) return value[key];
  return [];
}

function setOptions(element, items, placeholder) {
  element.innerHTML = `<option value="">${escapeHtml(placeholder)}</option>`;
  for (const item of items) {
    const option = document.createElement('option');
    option.value = String(item.value);
    option.textContent = item.label;
    if (item.slug) option.dataset.slug = String(item.slug);
    if (item.name) option.dataset.name = String(item.name);
    element.appendChild(option);
  }
}

function normaliseTimeframes(value) {
  return [...new Set(list(value).map(item => {
    if (item && typeof item === 'object') return item.value || item.name || item.code || item.timeframe;
    return item;
  }).map(item => String(item ?? '').trim()).filter(Boolean))];
}

function marketValue(item) {
  return String(item?.symbol || item?.name || item?.code || item?.instrument || item?.market_symbol || '').trim();
}

function updateRangeNote() {
  const start = form.elements.start_date?.value;
  const end = form.elements.end_date?.value;
  const note = $('[data-backtest-range]');
  if (note) note.textContent = start && end
    ? `Historical boundary: ${start} → ${end}. Only broker data inside this exact interval will be evaluated.`
    : 'Choose a broker instrument, timeframe, and exact historical interval.';
}

function refreshTimeframes(preferred = '') {
  const market = marketMeta[symbol.value];
  const marketFrames = normaliseTimeframes(market?.supported_timeframes || market?.timeframes || market?.available_timeframes);
  const frames = marketFrames.length ? marketFrames : (catalogueTimeframes.length ? catalogueTimeframes : DEFAULT_TIMEFRAMES);
  setOptions(timeframe, frames.map(value => ({value, label: value})), 'Select broker-supported timeframe…');
  timeframe.value = preferred && frames.includes(preferred) ? preferred : (frames[0] || '');
  updateRangeNote();
}

async function loadStrategies() {
  const payload = await request('/api/strategies/available/');
  strategyCatalog = list(payload?.strategies, ['results','data','items']).filter(item => item?.enabled !== false);
  const options = strategyCatalog.map(item => ({
    value: String(item.id),
    label: `${item.name || item.slug || 'Strategy'}${item.version ? ` v${item.version}` : ''}`,
    slug: item.slug,
    name: item.name,
  })).filter(item => item.value && item.value !== 'undefined');
  setOptions(strategy, options, 'Select strategy from catalog…');
  hydrateStrategySelection();
  return options;
}

async function loadBrokerCatalogue() {
  let payload;
  try {
    payload = await request('/api/market/broker-catalogue/');
  } catch (primaryError) {
    payload = await request('/market-catalogue/');
  }

  const items = list(payload?.symbols, ['results','data','items','markets']);
  const options = items.map(item => {
    const value = marketValue(item);
    return {
      value,
      label: `${item?.display_name || item?.name || value} — ${value}`,
      raw: item,
    };
  }).filter(item => item.value);

  marketMeta = {};
  for (const item of options) marketMeta[item.value] = item.raw;
  catalogueTimeframes = normaliseTimeframes(payload?.supported_timeframes);
  setOptions(symbol, options, 'Select broker instrument…');
  refreshTimeframes();
  hydrateFromQuery();
  return options;
}

function hydrateStrategySelection() {
  const query = new URLSearchParams(window.location.search);
  const requested = String(query.get('strategy_id') || query.get('strategy') || '').trim().toLowerCase();
  if (!requested) return;
  const match = strategyCatalog.find(item => [item.id, item.slug, item.name].some(value => String(value ?? '').trim().toLowerCase() === requested));
  if (match) strategy.value = String(match.id);
}

function hydrateFromQuery() {
  const query = new URLSearchParams(window.location.search);
  const selectedSymbol = query.get('symbol');
  const selectedTimeframe = query.get('timeframe');
  if (selectedSymbol && [...symbol.options].some(option => option.value === selectedSymbol)) symbol.value = selectedSymbol;
  refreshTimeframes(selectedTimeframe || '');
}

async function hydrateFromStrategyCenter() {
  if (new URLSearchParams(window.location.search).has('strategy') || new URLSearchParams(window.location.search).has('strategy_id')) return;
  try {
    const payload = await request('/api/strategies/current/', {}, 10000);
    const config = payload?.configuration;
    if (!config) return;
    const match = strategyCatalog.find(item => String(item.id) === String(payload?.strategy?.id) || String(item.slug).toLowerCase() === String(payload?.strategy?.slug || '').toLowerCase());
    if (match) strategy.value = String(match.id);
    if (config.symbol && [...symbol.options].some(option => option.value === String(config.symbol))) symbol.value = String(config.symbol);
    refreshTimeframes(config.timeframe || '');
  } catch (_) {
    // Backtesting remains usable from its own catalog even if no current strategy is configured.
  }
}

function render() {
  const columns = [
    ['strategy','Strategy'], ['symbol','Symbol'], ['timeframe','Timeframe'],
    ['start_date','Start'], ['end_date','End'], ['status','Status'],
    ['net_profit','Net profit'], ['total_trades','Trades'],
    ['strategy_confidence','Confidence'], ['created_at','Created'],
  ];
  table.innerHTML = `<thead><tr>${columns.map(column => `<th>${column[1]}</th>`).join('')}<th>Options</th></tr></thead><tbody></tbody>`;
  const body = $('tbody', table);
  body.innerHTML = rows.length ? rows.map(item => {
    const result = item.result_snapshot?.result || item.result_snapshot || {};
    const net = result.net_profit ?? result.total_profit ?? '—';
    const trades = result.total_trades ?? (Array.isArray(result.trades) ? result.trades.length : '—');
    const confidence = result.strategy_confidence != null ? `${result.strategy_confidence}%` : '—';
    const status = String(item.status || '').toLowerCase();
    return `<tr data-search="${escapeHtml(`${item.strategy || ''} ${item.symbol || ''}`.toLowerCase())}">
      ${columns.map(([key]) => {
        let value = item[key];
        if (key === 'net_profit') value = net;
        if (key === 'total_trades') value = trades;
        if (key === 'strategy_confidence') value = confidence;
        return `<td>${escapeHtml(value ?? '—')}</td>`;
      }).join('')}
      <td class="backtest-actions">
        <button type="button" class="btn ghost" data-results="${escapeHtml(item.id)}">View Results</button>
        ${status === 'pending' ? '<button type="button" class="btn ghost" data-edit="'+escapeHtml(item.id)+'">Edit</button>' : ''}
        ${['pending','running'].includes(status) ? '<button type="button" class="btn ghost" data-cancel="'+escapeHtml(item.id)+'">Cancel</button>' : ''}
        ${['failed','cancelled'].includes(status) ? '<button type="button" class="btn ghost" data-retry="'+escapeHtml(item.id)+'">Retry</button>' : ''}
        <button type="button" class="btn danger" data-delete="${escapeHtml(item.id)}">Delete</button>
      </td>
    </tr>`;
  }).join('') : '<tr><td colspan="11">No backtests yet. Configure a saved strategy and run your first research job.</td></tr>';

  const set = (selector, value) => { const element = $(selector); if (element) element.textContent = value; };
  set('[data-backtest-count]', rows.length);
  set('[data-backtest-completed]', rows.filter(item => String(item.status).toLowerCase() === 'completed').length);
  set('[data-backtest-running]', rows.filter(item => ['running','pending'].includes(String(item.status).toLowerCase())).length);
  set('[data-backtest-failed]', rows.filter(item => ['failed','cancelled'].includes(String(item.status).toLowerCase())).length);
}

function showMessage(message) {
  table.innerHTML = `<tbody><tr><td colspan="11" class="backtest-loading-row">${escapeHtml(message)}</td></tr></tbody>`;
}

async function loadHistory() {
  try {
    rows = list(await request('/api/backtests/'), ['results','data','items']);
    render();
  } catch (error) {
    showMessage(`Unable to load backtest history: ${error.message}`);
  }
}

async function poll(id) {
  for (let attempt = 0; attempt < 900; attempt += 1) {
    const item = await request(`/api/backtests/${encodeURIComponent(id)}/`);
    rows = [item, ...rows.filter(row => String(row.id) !== String(id))];
    render();
    if (['completed','failed','cancelled'].includes(String(item.status).toLowerCase())) return item;
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  throw new Error('Worker timeout; use Refresh to check the saved job.');
}

symbol.addEventListener('change', () => refreshTimeframes());
['start_date','end_date'].forEach(name => form.elements[name]?.addEventListener('input', updateRangeNote));

form.addEventListener('submit', async event => {
  event.preventDefault();
  const start = new Date(form.elements.start_date.value);
  const end = new Date(form.elements.end_date.value);
  if (!strategy.value || !symbol.value || !timeframe.value) {
    showMessage('Select strategy, broker instrument, and supported timeframe.');
    return;
  }
  if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) {
    showMessage('End date/time must be later than start date/time.');
    return;
  }

  const button = form.querySelector('button[type="submit"]');
  if (button) { button.disabled = true; button.textContent = 'Submitting…'; }
  try {
    const payload = Object.fromEntries(new FormData(form).entries());
    const selectedOption = strategy.options[strategy.selectedIndex];
    const selectedStrategy = strategyCatalog.find(item => String(item.id) === String(strategy.value));
    payload.strategy = selectedStrategy?.name || selectedOption?.dataset.name || selectedOption?.textContent?.replace(/\s+v\S+$/, '').trim();
    payload.strategy_id = strategy.value;
    delete payload.strategy_id;
    const result = await request('/api/backtests/', {
      method: 'POST',
      headers: {'Content-Type':'application/json', 'X-CSRFToken':csrf()},
      body: JSON.stringify(payload),
    });
    if (!result.id) throw new Error('Server did not return a backtest job id.');
    showMessage(`Backtest queued for ${payload.start_date} → ${payload.end_date}.`);
    const done = await poll(result.id);
    showMessage(String(done.status).toLowerCase() === 'completed' ? 'Backtest completed; results loaded below.' : `Backtest ${done.status}; recorded details loaded below.`);
    await loadHistory();
  } catch (error) {
    showMessage(`Backtest failed: ${error.message || 'request failed'}`);
  } finally {
    if (button) { button.disabled = false; button.textContent = 'Run backtest'; }
  }
});

table.addEventListener('click', async event => {
  const target = event.target.closest('[data-edit],[data-delete],[data-results],[data-cancel],[data-retry]');
  if (!target) return;
  const id = target.dataset.edit || target.dataset.delete || target.dataset.results || target.dataset.cancel || target.dataset.retry;
  const item = rows.find(row => String(row.id) === String(id));
  if (!item) return;

  try {
    if (target.dataset.results) {
      const detail = await request(`/api/backtests/${encodeURIComponent(id)}/results/`);
      showMessage(JSON.stringify(detail.result_snapshot || detail.statistics || detail));
      return;
    }
    if (target.dataset.cancel) {
      if (!window.confirm('Cancel this backtest?')) return;
      await request(`/api/backtests/${encodeURIComponent(id)}/cancel/`, {method:'POST', headers:{'X-CSRFToken':csrf()}});
      await loadHistory();
      return;
    }
    if (target.dataset.retry) {
      await request(`/api/backtests/${encodeURIComponent(id)}/retry/`, {method:'POST', headers:{'X-CSRFToken':csrf()}});
      await loadHistory();
      await poll(id);
      return;
    }
    if (target.dataset.delete) {
      if (!window.confirm('Delete this backtest and its recorded results?')) return;
      await request(`/api/backtests/${encodeURIComponent(id)}/`, {method:'DELETE', headers:{'X-CSRFToken':csrf()}});
      await loadHistory();
      return;
    }

    const start = window.prompt('Start date/time (YYYY-MM-DDTHH:MM)', String(item.start_date || '').slice(0,16));
    const end = window.prompt('End date/time (YYYY-MM-DDTHH:MM)', String(item.end_date || '').slice(0,16));
    if (!start || !end || new Date(end) <= new Date(start)) {
      showMessage('End date/time must be later than start date/time.');
      return;
    }
    await request(`/api/backtests/${encodeURIComponent(id)}/`, {
      method:'PATCH',
      headers:{'Content-Type':'application/json', 'X-CSRFToken':csrf()},
      body:JSON.stringify({start_date:start, end_date:end}),
    });
    await loadHistory();
  } catch (error) {
    showMessage(`Backtest action failed: ${error.message || 'request failed'}`);
  }
});

$('[data-backtest-search]')?.addEventListener('input', event => {
  const query = event.target.value.trim().toLowerCase();
  table.querySelectorAll('[data-search]').forEach(row => { row.hidden = !row.dataset.search.includes(query); });
});
$('[data-backtest-refresh]')?.addEventListener('click', loadHistory);

(async () => {
  const results = await Promise.allSettled([loadStrategies(), loadBrokerCatalogue(), loadHistory()]);
  await hydrateFromStrategyCenter();
  const catalogueResult = results[1];
  if (catalogueResult?.status === 'rejected') {
    setOptions(symbol, [], 'Broker catalogue unavailable — connect and refresh');
    setOptions(timeframe, DEFAULT_TIMEFRAMES.map(value => ({value, label:value})), 'Select timeframe…');
    showMessage(`Unable to load broker/strategy catalog: ${catalogueResult.reason?.message || 'broker catalogue request failed'}`);
  }
})();
})();
