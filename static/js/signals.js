(() => {
  'use strict';
  if (window.__algoBotLiveSignalsPage) return;
  window.__algoBotLiveSignalsPage = true;

  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const num = (value, digits = 5) => value == null || Number.isNaN(Number(value))
    ? '—'
    : Number(value).toLocaleString(undefined, {maximumFractionDigits: digits});
  const pct = value => value == null || Number.isNaN(Number(value)) ? '—' : `${Number(value).toFixed(1)}%`;
  const label = value => String(value ?? '').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase()) || '—';
  const tone = value => {
    const v = String(value || '').toUpperCase();
    return v === 'BUY' ? 'buy' : v === 'SELL' ? 'sell' : 'hold';
  };
  const stateText = value => String(value || 'WAITING').replaceAll('_', ' ');
  const S = {rows: [], scanning: false, page: 1, contractRequest: 0};

let ContractPicker={capabilities:null,selected:null,requestId:0};
async function loadSignalContract(){const row= S.rows.find(r=>r.symbol===($('signalsSymbol')?.value||'')) || S.rows.find(r=>r.execution_ready) || S.rows[0];const symbol=row?.symbol;if(!symbol){$('signalsContractStatus').textContent='Select or scan a market first.';return}const id=++ContractPicker.requestId;$('signalsContractStatus').textContent='Loading current Deriv contracts_for…';try{const data=await request('/analysis/contracts/?symbol='+encodeURIComponent(symbol)+'&timeframe='+encodeURIComponent(row?.timeframe||$('signalsTimeframe')?.value||'M1'));if(id!==ContractPicker.requestId)return;ContractPicker.capabilities=data.capabilities||{};const rows=ContractPicker.capabilities.available||[];const account=data.account||{};const fill=(el,vals,placeholder)=>{const current=el.value;el.innerHTML='<option value="">'+esc(placeholder)+'</option>'+[...new Set(vals.filter(Boolean))].sort().map(v=>'<option value="'+esc(v)+'">'+esc(label(v))+'</option>').join('');if(vals.includes(current))el.value=current};fill($('signalsContractFamily'),rows.map(x=>x.contract_category),'All broker families');fill($('signalsContractExpiry'),rows.map(x=>x.expiry_type),'Any broker expiry');fill($('signalsContractSentiment'),rows.map(x=>x.sentiment),'Any broker sentiment');const marketTypes=ContractPicker.capabilities.market_types||[];const submarkets=ContractPicker.capabilities.submarkets||[];$('signalsContractMarketType').innerHTML='<option>'+esc(marketTypes[0]||row?.market||'—')+'</option>';$('signalsContractSubMarket').innerHTML='<option>'+esc(submarkets[0]||row?.sub_market||'—')+'</option>';renderSignalContractTypes();$('signalsContractStatus').textContent='Broker account '+(account.account_type||'—')+' · '+(account.currency||'—')+' · credentials '+(account.credential_status||'unavailable')+' · contract capabilities loaded';$('signalsContractNote').textContent='Broker-published: family, type, expiry and sentiment. Duration, barrier, multiplier and growth-rate inputs are not asserted as supported until Deriv validates a concrete proposal.'}catch(e){$('signalsContractStatus').textContent=e.message||'Broker capabilities unavailable';$('signalsContractNote').textContent='No contract choice has been fabricated.'}}
function renderSignalContractTypes(){const rows=ContractPicker.capabilities?.available||[];const f=$('signalsContractFamily').value,e=$('signalsContractExpiry').value,s=$('signalsContractSentiment').value;const types=rows.filter(x=>(!f||x.contract_category===f)&&(!e||x.expiry_type===e)&&(!s||x.sentiment===s)).map(x=>x.contract_type);const el=$('signalsContractType');el.innerHTML='<option value="">Select contract type</option>'+[...new Set(types.filter(Boolean))].sort().map(v=>'<option value="'+esc(v)+'">'+esc(v)+'</option>').join('')}
function applySignalContract(){const type=$('signalsContractType').value;if(!type){$('signalsContractSummary').textContent='No broker contract selected.';return}const rows=ContractPicker.capabilities?.available||[];const chosen=rows.find(x=>x.contract_type===type&&(!$('signalsContractFamily').value||x.contract_category===$('signalsContractFamily').value)&&(!$('signalsContractExpiry').value||x.expiry_type===$('signalsContractExpiry').value)&&(!$('signalsContractSentiment').value||x.sentiment===$('signalsContractSentiment').value));if(!chosen)return;ContractPicker.selected={...chosen,duration:$('signalsContractDuration').value||null,duration_unit:$('signalsContractDurationUnit').value||null,barrier:$('signalsContractBarrier').value||null,multiplier:$('signalsContractMultiplier').value||null,growth_rate:$('signalsContractGrowthRate').value||null};$('signalsContractSummary').textContent=chosen.contract_category+' · '+chosen.contract_type+' · '+(chosen.expiry_type||'expiry not published')+' · '+(chosen.sentiment||'sentiment not published');$('signalsContractModal').hidden=true;$('signalsContractModal').setAttribute('aria-hidden','true')}


  async function getApiClient() {
    if (window.AlgoBotAPI?.apiClient) return window.AlgoBotAPI.apiClient;
    await new Promise(resolve => {
      let done = false;
      const finish = () => { if (!done) { done = true; resolve(); } };
      window.addEventListener('algobot:api-ready', finish, {once: true});
      setTimeout(finish, 1200);
    });
    return window.AlgoBotAPI?.apiClient || null;
  }

  async function request(path) {
    const client = await getApiClient();
    if (client) return client.get(path, {credentials: 'include', __algoTimeoutMs: 15000});
    const response = await fetch(new URL(path, window.location.origin), {
      method: 'GET',
      credentials: 'include',
      headers: {'Accept': 'application/json'}
    });
    let payload = {};
    try { payload = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(payload?.message || `Signals API request failed (${response.status})`);
    return payload;
  }

  function populateSelect(id, values, emptyLabel) {
    const el = $(id);
    if (!el) return;
    const current = el.value;
    el.innerHTML = `<option value="">${esc(emptyLabel)}</option>` +
      values.map(v => `<option value="${esc(v)}">${esc(label(v))}</option>`).join('');
    if (values.includes(current)) el.value = current;
  }

  function populateFilters(rows) {
    populateSelect('signalsStrategy', [...new Set(rows.map(r => r.strategy).filter(Boolean))].sort(), 'All strategies');
    populateSelect('signalsStatus', [...new Set(rows.map(r => r.status).filter(Boolean))].sort(), 'All statuses');
    const symbol = $('signalsSymbol');
    if (symbol) {
      const current = symbol.value;
      const values = [...new Map(rows.map(r => [r.symbol, r])).values()];
      symbol.innerHTML = '<option value="">All instruments</option>' +
        values.map(r => `<option value="${esc(r.symbol)}">${esc(r.symbol)} · ${esc(r.display_name || r.instrument)}</option>`).join('');
      if (values.some(r => r.symbol === current)) symbol.value = current;
    }
  }

  function filteredRows() {
    const q = String($('signalsSearch')?.value || '').trim().toLowerCase();
    const symbol = $('signalsSymbol')?.value || '';
    const strategy = $('signalsStrategy')?.value || '';
    const direction = String($('signalsDirection')?.value || '').toUpperCase();
    const status = $('signalsStatus')?.value || '';
    const minimum = Number($('signalsConfidence')?.value || 0);
    const sort = $('signalsSort')?.value || 'symbol';

    const rows = S.rows.filter(r => {
      const hay = [r.symbol, r.display_name, r.strategy, r.status, r.market].filter(Boolean).join(' ').toLowerCase();
      return (!q || hay.includes(q)) &&
        (!symbol || r.symbol === symbol) &&
        (!strategy || r.strategy === strategy) &&
        (!direction || String(r.direction || '').toUpperCase() === direction) &&
        (!status || r.status === status) &&
        (!minimum || Number(r.confidence) >= minimum);
    });

    rows.sort((a, b) => {
      if (sort === 'confidence') return (Number(b.confidence) || -Infinity) - (Number(a.confidence) || -Infinity);
      if (sort === 'live_age') return (Number(a.live?.age_seconds) || Infinity) - (Number(b.live?.age_seconds) || Infinity);
      if (sort === 'timestamp') return String(b.analysis_timestamp || '').localeCompare(String(a.analysis_timestamp || ''));
      return String(a.symbol || '').localeCompare(String(b.symbol || ''));
    });

    const size = Number($('signalsPageSize')?.value || 20);
    const pages = Math.max(1, Math.ceil(rows.length / size));
    S.page = Math.min(Math.max(1, S.page), pages);
    const start = (S.page - 1) * size;
    if ($('signalsPrev')) $('signalsPrev').disabled = S.page <= 1;
    if ($('signalsNext')) $('signalsNext').disabled = S.page >= pages;
    if ($('signalsPager')) $('signalsPager').textContent = `Page ${S.page} of ${pages} · ${rows.length} matching`;
    return rows.slice(start, start + size);
  }

  function renderTable(rows) {
    const tbody = $('signalsTable');
    if (!tbody) return;
    tbody.innerHTML = rows.map(row => `<tr data-symbol="${esc(row.symbol)}">
      <td><strong>${esc(row.display_name || row.symbol)}</strong><small>${esc(row.symbol)}</small></td>
      <td>${esc(row.market || '—')}<small>${esc(row.sub_market || '')}</small></td>
      <td>${esc(row.timeframe || '—')}</td>
      <td>${esc(num(row.live?.price))}</td>
      <td class="${tone(row.baseline_direction)}">${esc(row.baseline_direction || '—')}</td>
      <td class="${tone(row.direction)}">${esc(row.direction || '—')}</td>
      <td><strong>${esc(pct(row.confidence))}</strong></td>
      <td><span class="status-pill ${tone(row.direction)}">${esc(stateText(row.status))}</span></td>
    </tr>`).join('') || '<tr><td colspan="8">No research rows match the selected filters.</td></tr>';

    tbody.querySelectorAll('tr[data-symbol]').forEach(row => {
      row.addEventListener('click', () => focus(S.rows.find(item => item.symbol === row.dataset.symbol) || null));
    });
  }

  function renderTape(rows) {
    const tape = $('liveTape');
    if (!tape) return;
    $('marketCount').textContent = `${rows.length} markets`;
    tape.innerHTML = rows.slice(0, 20).map(row => `<button type="button" class="tape-row" data-symbol="${esc(row.symbol)}">
      <span><strong>${esc(row.symbol)}</strong><small>${esc(row.market || 'Deriv')}</small></span>
      <strong>${esc(num(row.live?.price))}</strong>
      <span class="tape-signal ${tone(row.direction)}">${esc(row.direction || '—')}</span>
      <span>${esc(pct(row.confidence))}</span>
    </button>`).join('') || '<div class="empty">No current Deriv quotes returned for this scan.</div>';
    tape.querySelectorAll('[data-symbol]').forEach(button => {
      button.addEventListener('click', () => focus(S.rows.find(r => r.symbol === button.dataset.symbol) || null));
    });
  }

  function renderEvidence(row) {
    const why = $('signalWhy');
    const source = $('whySource');
    if (!row) {
      if (source) source.textContent = 'Select a signal';
      if (why) why.innerHTML = '<p class="muted">Select a market to inspect persisted strategy evidence.</p>';
      return;
    }
    if (source) source.textContent = row.strategy ? `Strategy · ${row.strategy_version || 'persisted'}` : 'Market state';
    const items = Array.isArray(row.why) ? row.why : [];
    const base = [
      ['Broker account', row.account_id ? `${row.account_type || 'account'} · ${row.account_id}` : null, row.broker],
      ['Market data', row.live?.source, row.live?.epoch ? new Date(Number(row.live.epoch) * 1000).toLocaleString() : null],
      ['Signal state', row.status, row.analysis_timestamp],
      ['Confirmation', Array.isArray(row.evidence) ? row.evidence.join(', ') : null, row.execution_ready ? 'PASS' : 'WAIT']
    ];
    const all = [...base, ...items.map(item => [item.condition, item.observed, item.result])]
      .filter(item => item[1] !== null && item[1] !== undefined && item[1] !== '');
    if (why) {
      why.innerHTML = all.length
        ? all.map(item => `<div class="evidence-row"><span>${esc(label(item[0]))}</span><strong>${esc(typeof item[1] === 'object' ? JSON.stringify(item[1]) : item[1])}</strong><small>${esc(item[2] || 'OBSERVED')}</small></div>`).join('')
        : '<p class="muted">No persisted evidence is available for this signal.</p>';
    }
  }

  async function renderValidatedContract(row) {
    const requestId = ++S.contractRequest;
    const type = $('focusContract');
    const family = $('focusContractFamily');
    const reason = $('focusContractReason');
    if (!row || !row.direction || !['BUY', 'SELL'].includes(String(row.direction).toUpperCase())) {
      if (type) type.textContent = 'Not selected';
      if (family) family.textContent = 'Not selected';
      if (reason) reason.textContent = 'A contract is not selected until a validated BUY/SELL research direction exists.';
      return;
    }
    if (type) type.textContent = 'Checking broker capabilities…';
    if (family) family.textContent = 'Checking broker capabilities…';
    try {
      const data = await request(`/analysis/contracts/?symbol=${encodeURIComponent(row.symbol)}&direction=${encodeURIComponent(row.direction)}&timeframe=${encodeURIComponent(row.timeframe || 'M1')}`);
      if (requestId !== S.contractRequest) return;
      const selected = data.selected_contract;
      if (!selected) {
        if (type) type.textContent = 'Unavailable';
        if (family) family.textContent = 'Unavailable';
        if (reason) reason.textContent = 'Deriv returned no direction-compatible contract for this research state.';
        return;
      }
      if (type) type.textContent = selected.contract_type;
      if (family) family.textContent = selected.contract_family;
      if (reason) reason.textContent = `Validated by current Deriv contracts_for data · ${selected.selection_basis}. This is not a profitability or seasonal ranking.`;
    } catch (_) {
      if (requestId !== S.contractRequest) return;
      if (type) type.textContent = 'Unavailable';
      if (family) family.textContent = 'Unavailable';
      if (reason) reason.textContent = 'Broker contract capabilities are currently unavailable.';
    }
  }

  function focus(row) {
    if (!row) {
      ['focusInstrument','focusPrice','focusSource','focusBaseline','focusDirection','focusThreshold','focusAge','focusEntry','focusStop','focusTake','focusTf'].forEach(id => { if ($(id)) $(id).textContent = '—'; });
      if ($('focusInstrument')) $('focusInstrument').textContent = 'Select a market';
      if ($('focusState')) { $('focusState').textContent = 'WAITING'; $('focusState').className = 'signal-state waiting'; }
      if ($('focusConfidence')) $('focusConfidence').textContent = '—';
      if ($('focusConfidenceBar')) $('focusConfidenceBar').style.width = '0%';
      if ($('focusEvidence')) $('focusEvidence').innerHTML = '<span class="muted">Select a market to inspect its live state.</span>';
      renderEvidence(null);
      renderValidatedContract(null);
      return;
    }
    $('focusInstrument').textContent = row.display_name || row.instrument || row.symbol || '—';
    $('focusState').textContent = stateText(row.status);
    $('focusState').className = `signal-state ${tone(row.direction)}${row.status === 'WAITING_FOR_ANALYSIS' ? ' waiting' : ''}`;
    $('focusPrice').textContent = num(row.live?.price);
    $('focusSource').textContent = row.live?.source === 'deriv_public_websocket'
      ? `Deriv live · ${row.live?.epoch ? new Date(Number(row.live.epoch) * 1000).toLocaleTimeString() : 'now'}`
      : 'No live tick';
    $('focusConfidence').textContent = pct(row.confidence);
    const confidence = Number(row.confidence);
    $('focusConfidenceBar').style.width = Number.isFinite(confidence) ? `${Math.max(0, Math.min(100, confidence))}%` : '0%';
    $('focusBaseline').textContent = row.baseline_direction ? `${row.baseline_direction} · ${pct(row.baseline_confidence)}` : 'No baseline';
    $('focusDirection').textContent = row.direction || '—';
    $('focusDirection').className = tone(row.direction);
    $('focusThreshold').textContent = pct(row.live_confidence_threshold);
    $('focusAge').textContent = row.live?.age_seconds == null ? '—' : `${row.live.age_seconds}s`;
    $('focusEntry').textContent = num(row.entry_price);
    $('focusStop').textContent = num(row.stop_loss);
    $('focusTake').textContent = num(row.take_profit);
    $('focusTf').textContent = row.timeframe || '—';
    $('focusEvidence').innerHTML = (row.evidence || []).map(item => `<span class="evidence-chip">${esc(label(item))}</span>`).join('') || '<span class="muted">No confirmation evidence.</span>';
    renderEvidence(row);
    renderValidatedContract(row);
  }

  function renderHealth(data) {
    const live = Number(data.live_data_available_count || 0);
    const total = Number(data.count || 0);
    if ($('signalsAccount')) $('signalsAccount').textContent = data.account?.id || '—';
    if ($('signalsAccountType')) $('signalsAccountType').textContent = `${data.account?.type || 'account'} · ${data.account?.currency || ''}`;
    if ($('signalsFeed')) $('signalsFeed').textContent = data.broker_feed_state || (live === total && total ? 'LIVE' : live ? 'PARTIAL' : 'UNAVAILABLE');
    if ($('signalsFeedAge')) $('signalsFeedAge').textContent = live ? `${live}/${total} live Deriv quotes · ${num(data.feed_latency_ms, 0)} ms` : 'No current Deriv quotes received';
    if ($('signalsReady')) $('signalsReady').textContent = String(data.actionable_count ?? 0);
    if ($('signalsBaseline')) $('signalsBaseline').textContent = `${S.rows.filter(r => r.analysis_signal_id).length}/${S.rows.length} matched`;
    if ($('scanTimestamp')) $('scanTimestamp').textContent = `Scanned ${new Date().toLocaleTimeString()}`;
  }

  async function scan() {
    if (S.scanning) return;
    S.scanning = true;
    const buttons = [$('signalsScan'), $('signalsRefresh')].filter(Boolean);
    buttons.forEach(button => { button.disabled = true; button.setAttribute('aria-busy', 'true'); });
    const symbol = $('signalsSymbol')?.value || '';
    const timeframe = $('signalsTimeframe')?.value || 'M1';
    const limit = $('signalsLimit')?.value || '40';
    try {
      const data = await request(`/api/strategy-signals/?limit=${encodeURIComponent(limit)}&timeframe=${encodeURIComponent(timeframe)}${symbol ? `&symbol=${encodeURIComponent(symbol)}` : ''}`);
      if (data.status !== 'ok') throw new Error(data.message || 'Live signal service returned an invalid response.');
      S.rows = Array.isArray(data.data) ? data.data : [];
      S.page = 1;
      populateFilters(S.rows);
      renderHealth(data);
      renderView();
    } catch (error) {
      const message = error?.message || 'Market data unavailable.';
      S.rows = [];
      if ($('signalsFeed')) $('signalsFeed').textContent = 'UNAVAILABLE';
      if ($('signalsFeedAge')) $('signalsFeedAge').textContent = message;
      if ($('signalsReady')) $('signalsReady').textContent = '0';
      if ($('signalsBaseline')) $('signalsBaseline').textContent = 'Unavailable';
      if ($('scanTimestamp')) $('scanTimestamp').textContent = `Scan failed · ${new Date().toLocaleTimeString()}`;
      renderTable([]);
      renderTape([]);
      focus(null);
    } finally {
      S.scanning = false;
      buttons.forEach(button => { button.disabled = false; button.removeAttribute('aria-busy'); });
    }
  }

  function renderView() {
    const rows = filteredRows();
    renderTape(rows);
    renderTable(rows);
    focus(rows.find(r => r.execution_ready) || rows.find(r => r.direction === 'BUY' || r.direction === 'SELL') || rows.find(r => r.live) || rows[0] || null);
  }

  function boot() {
    $('signalsContractOpen')?.addEventListener('click',()=>{const m=$('signalsContractModal');m.hidden=false;m.setAttribute('aria-hidden','false');loadSignalContract()});
    $('signalsContractClose')?.addEventListener('click',()=>{const m=$('signalsContractModal');m.hidden=true;m.setAttribute('aria-hidden','true')});
    document.querySelectorAll('[data-signal-contract-close]').forEach(e=>e.addEventListener('click',()=>{const m=$('signalsContractModal');m.hidden=true;m.setAttribute('aria-hidden','true')}));
    $('signalsContractApply')?.addEventListener('click',applySignalContract);
    $('signalsContractClear')?.addEventListener('click',()=>{ContractPicker.selected=null;$('signalsContractSummary').textContent='No contract selected.'});
    ['signalsContractFamily','signalsContractExpiry','signalsContractSentiment'].forEach(id=>$(id)?.addEventListener('change',renderSignalContractTypes));
    $('signalsScan')?.addEventListener('click', scan);
    $('signalsRefresh')?.addEventListener('click', scan);
    $('signalsSymbol')?.addEventListener('change', () => { S.page = 1; renderView(); });
    $('signalsTimeframe')?.addEventListener('change', scan);
    $('signalsLimit')?.addEventListener('change', scan);
    ['signalsSearch','signalsStrategy','signalsDirection','signalsStatus','signalsConfidence','signalsSort','signalsPageSize']
      .forEach(id => $(id)?.addEventListener('input', () => { S.page = 1; renderView(); }));
    $('signalsPrev')?.addEventListener('click', () => { if (S.page > 1) { S.page -= 1; renderView(); } });
    $('signalsNext')?.addEventListener('click', () => { S.page += 1; renderView(); });
    scan();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
