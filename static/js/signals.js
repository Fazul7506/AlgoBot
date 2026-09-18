(() => {
  'use strict';
  if (window.__algoBotLiveSignalsPage) return;
  window.__algoBotLiveSignalsPage = true;
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const num = (value, digits = 5) => value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toLocaleString(undefined, {maximumFractionDigits: digits});
  const pct = value => value == null || Number.isNaN(Number(value)) ? '—' : `${Number(value).toFixed(1)}%`;
  const label = value => String(value ?? '').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase()) || '—';
  const tone = value => { const v = String(value || '').toUpperCase(); return v === 'BUY' ? 'buy' : v === 'SELL' ? 'sell' : 'hold'; };
  const stateText = value => String(value || 'WAITING').replaceAll('_', ' ');
  const S = { rows: [], last: null, scanning: false };

  function setStatus(message, live = false) {
    if ($('signalsFeed')) $('signalsFeed').textContent = message;
    if ($('signalsFeedAge')) $('signalsFeedAge').textContent = live ? 'Fresh authenticated Deriv snapshot' : 'Waiting for broker snapshot';
  }
  function apiBase() {
    const configured = (document.querySelector('meta[name="algobot-api-base"]')?.content || '').trim();
    return (configured || window.location.origin).replace(/\/+$/, '');
  }
  async function getApiClient() {
    if (window.AlgoBotAPI?.apiClient) return window.AlgoBotAPI.apiClient;
    // The page must remain functional if another deferred shell script delays the
    // canonical client. api_client.js also emits this event when it finishes.
    await new Promise(resolve => { let done = false; const finish = () => { if (!done) { done = true; resolve(); } }; window.addEventListener('algobot:api-ready', finish, {once:true}); setTimeout(finish, 1200); });
    return window.AlgoBotAPI?.apiClient || null;
  }
  async function request(path) {
    const client = await getApiClient();
    if (client) return client.get(path, {credentials:'include', __algoTimeoutMs:15000});
    // Read-only fallback: keep Signals usable even when the shared client did not
    // initialise. This never changes mutation/authentication behaviour.
    const rawPath = String(path || '/');
    const selectedId = window.AlgoBotAccountContext?.getSelectedId?.() || window.AlgoBotBrokerState?.get?.()?.account?.id;
    const headers = new Headers({'Accept':'application/json'});
    if (selectedId != null) headers.set('X-Algobot-Account-ID', String(selectedId));
    const response = await fetch(new URL(rawPath, `${apiBase()}/`).toString(), {method:'GET', credentials:'include', headers});
    let payload = {};
    try { payload = await response.json(); } catch (_) { payload = {detail: await response.text()}; }
    if (!response.ok) throw new Error(payload?.message || payload?.detail || `Signals API request failed (${response.status})`);
    return payload;
  }
  function populateSymbols(rows) {
    const select = $('signalsSymbol'); if (!select) return;
    const current = select.value; const symbols = [...new Map(rows.map(row => [row.symbol, row])).values()];
    select.innerHTML = '<option value="">All instruments</option>' + symbols.map(row => `<option value="${esc(row.symbol)}">${esc(row.symbol)} · ${esc(row.display_name || row.instrument)}</option>`).join('');
    if (symbols.some(row => row.symbol === current)) select.value = current;
  }
  function setSpec(id, value) { if ($(id)) $(id).textContent = value == null || value === '' ? 'Not specified' : label(value); }
  function renderSpec(row) {
    const c = row?.trade_context || {};
    setSpec('specMarketType', c.market_type || row?.market); setSpec('specSubMarket', c.sub_market || row?.sub_market); setSpec('specInstrument', c.instrument || row?.symbol);
    setSpec('specTradeType', c.trade_type); setSpec('specDirection', c.direction || row?.direction); setSpec('specContractType', c.contract_type); setSpec('specContractFamily', c.contract_family);
    setSpec('specDuration', c.duration); setSpec('specDurationUnit', c.duration_unit); setSpec('specBarrier', c.barrier); setSpec('specStake', c.stake); setSpec('specPayout', c.payout);
    setSpec('specStrategy', c.strategy); setSpec('specCategory', c.strategy_category); setSpec('specRisk', c.risk_profile); setSpec('specExecution', c.execution_mode);
    setSpec('specEntryCondition', c.entry_condition); setSpec('specConfirmation', c.confirmation); setSpec('specRegime', c.market_regime); setSpec('specQuoteSource', c.quote_type || row?.source);
    if ($('specSource')) $('specSource').textContent = row ? `${c.broker || 'Deriv'} · ${c.account_type || 'account'} · ${c.currency || ''}` : 'Awaiting signal';
  }
  function focus(row) {
    if (!row) {
      ['focusInstrument','focusPrice','focusSource','focusBaseline','focusDirection','focusThreshold','focusAge','focusEntry','focusStop','focusTake','focusTf'].forEach(id => { if ($(id)) $(id).textContent = '—'; });
      if ($('focusInstrument')) $('focusInstrument').textContent = 'Select a market'; if ($('focusState')) { $('focusState').textContent='WAITING'; $('focusState').className='signal-state waiting'; }
      if ($('focusConfidence')) $('focusConfidence').textContent='0%'; if ($('focusConfidenceBar')) $('focusConfidenceBar').style.width='0%'; if ($('focusEvidence')) $('focusEvidence').innerHTML='<span class="muted">Select a market to inspect its live state.</span>'; renderSpec(null); return;
    }
    $('focusInstrument').textContent = row.display_name || row.instrument || row.symbol || '—'; $('focusState').textContent = stateText(row.status); $('focusState').className=`signal-state ${tone(row.direction)}${row.status==='WAITING_FOR_ANALYSIS'?' waiting':''}`;
    $('focusPrice').textContent=num(row.live?.price); $('focusSource').textContent=row.live?.source==='deriv_authenticated_websocket'?`Deriv live · ${row.live?.epoch?new Date(Number(row.live.epoch)*1000).toLocaleTimeString():'now'}`:'No live tick';
    $('focusConfidence').textContent=pct(row.confidence??0); $('focusConfidenceBar').style.width=`${Math.max(0,Math.min(100,Number(row.confidence)||0))}%`; $('focusBaseline').textContent=row.baseline_direction?`${row.baseline_direction} · ${pct(row.baseline_confidence)}`:'No baseline';
    $('focusDirection').textContent=row.direction||'HOLD'; $('focusDirection').className=tone(row.direction); $('focusThreshold').textContent=pct(row.live_confidence_threshold); $('focusAge').textContent=row.live?.age_seconds==null?'—':`${row.live.age_seconds}s`;
    $('focusEntry').textContent=num(row.entry_price); $('focusStop').textContent=num(row.stop_loss); $('focusTake').textContent=num(row.take_profit); $('focusTf').textContent=row.timeframe||'—'; $('focusEvidence').innerHTML=(row.evidence||[]).map(item=>`<span class="evidence-chip">${esc(stateText(item))}</span>`).join('')||'<span class="muted">No confirmation evidence.</span>'; renderSpec(row);
  }
  function renderTape(rows) {
    const el=$('liveTape'); if(!el)return; $('marketCount').textContent=`${rows.length} markets`;
    el.innerHTML=rows.slice(0,20).map(row=>`<button type="button" class="tape-row" data-symbol="${esc(row.symbol)}"><span><strong>${esc(row.symbol)}</strong><small>${esc(row.market||'Deriv')}</small></span><strong>${esc(num(row.live?.price))}</strong><span class="tape-signal ${tone(row.direction)}">${esc(row.direction||'HOLD')}</span><span>${esc(pct(row.confidence))}</span></button>`).join('')||'<div class="empty">No broker quotes returned for this scan.</div>';
    el.querySelectorAll('[data-symbol]').forEach(b=>b.addEventListener('click',()=>focus(S.rows.find(r=>r.symbol===b.dataset.symbol))));
  }
  function renderTable(rows) {
    const tbody=$('signalsTable'); if(!tbody)return;
    tbody.innerHTML=rows.map(row=>{const c=row.trade_context||{};return `<tr data-symbol="${esc(row.symbol)}"><td><strong>${esc(row.display_name||row.symbol)}</strong><small>${esc(row.symbol)}</small></td><td>${esc(c.market_type||row.market||'—')}<small>${esc(c.sub_market||row.sub_market||'')}</small></td><td>${esc(c.trade_type||row.direction||'—')}</td><td>${esc(c.contract_type||'—')}</td><td>${esc(row.timeframe||'—')}</td><td>${esc(num(row.live?.price))}</td><td class="${tone(row.baseline_direction)}">${esc(row.baseline_direction||'—')}</td><td class="${tone(row.direction)}">${esc(row.direction||'HOLD')}</td><td><strong>${esc(pct(row.confidence))}</strong></td><td><span class="status-pill ${tone(row.direction)}">${esc(stateText(row.status))}</span></td></tr>`}).join('')||'<tr><td colspan="10">No broker signal rows returned.</td></tr>';
    tbody.querySelectorAll('tr[data-symbol]').forEach(r=>r.addEventListener('click',()=>focus(S.rows.find(item=>item.symbol===r.dataset.symbol))));
  }
  function renderHealth(data) {
    const live=Number(data.live_data_available_count||0), total=Number(data.count||0), stale=Number(data.stale_count||0); if($('signalsFeed'))$('signalsFeed').textContent=live===total&&total>0?'LIVE':live>0?'PARTIAL':'UNAVAILABLE'; if($('signalsFeedAge'))$('signalsFeedAge').textContent=live>0?`${live}/${total} live Deriv quotes · ${num(data.feed_latency_ms,0)} ms`:'No current Deriv quotes received'; if($('signalsReady'))$('signalsReady').textContent=String(data.actionable_count??0); if($('signalsBaseline'))$('signalsBaseline').textContent=`${S.rows.filter(r=>r.analysis_signal_id).length}/${S.rows.length} matched`; if($('scanTimestamp'))$('scanTimestamp').textContent=`Scanned ${new Date().toLocaleTimeString()}${stale?` · ${stale} stale`:''}`;
  }
  async function scan() {
    if(S.scanning)return; S.scanning=true; const controls=[$('signalsScan'),$('signalsRefresh')].filter(Boolean); controls.forEach(b=>{b.disabled=true;b.setAttribute('aria-busy','true')}); const symbol=$('signalsSymbol')?.value||'', timeframe=$('signalsTimeframe')?.value||'M1', limit=$('signalsLimit')?.value||'40';
    try { setStatus('Authenticating Deriv live feed…'); const data=await request(`/api/strategy-signals/?limit=${encodeURIComponent(limit)}&timeframe=${encodeURIComponent(timeframe)}${symbol?`&symbol=${encodeURIComponent(symbol)}`:''}`); if(data.status!=='ok')throw new Error(data.message||'Live signal service returned an invalid response.'); S.rows=Array.isArray(data.data)?data.data:[]; S.last=data; populateSymbols(S.rows); if($('signalsAccount'))$('signalsAccount').textContent=data.account?.id||'—'; if($('signalsAccountType'))$('signalsAccountType').textContent=`${data.account?.type||'account'} · ${data.account?.currency||''}`; renderHealth(data); setStatus(Number(data.live_data_available_count||0)>0?'LIVE':'NO LIVE QUOTES',Number(data.live_data_available_count||0)>0); renderTape(S.rows); renderTable(S.rows); focus(S.rows.find(r=>r.execution_ready)||S.rows.find(r=>r.direction==='BUY'||r.direction==='SELL')||S.rows.find(r=>r.live)||S.rows[0]); }
    catch(error){S.rows=[];setStatus(error?.message||'Authenticated Deriv live feed unavailable.');if($('signalsReady'))$('signalsReady').textContent='0';if($('signalsBaseline'))$('signalsBaseline').textContent='Unavailable';if($('scanTimestamp'))$('scanTimestamp').textContent=`Scan failed · ${new Date().toLocaleTimeString()}`;renderTape([]);renderTable([]);focus(null)}
    finally{S.scanning=false;controls.forEach(b=>{b.disabled=false;b.removeAttribute('aria-busy')})}
  }
  function boot(){ $('signalsScan')?.addEventListener('click',scan);$('signalsRefresh')?.addEventListener('click',scan);$('signalsSymbol')?.addEventListener('change',scan);$('signalsTimeframe')?.addEventListener('change',scan);$('signalsLimit')?.addEventListener('change',scan);window.addEventListener('algobot:account-synced',()=>{S.rows=[];setStatus('Account changed — authenticating the new Deriv feed…');scan()});window.addEventListener('algobot:account-changed',()=>{S.rows=[];setStatus('Account changed — authenticating the new Deriv feed…');scan()});scan(); }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
