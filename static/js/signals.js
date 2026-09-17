(() => {
  'use strict';
  if (window.__algoBotLiveSignalsPage) return;
  window.__algoBotLiveSignalsPage = true;

  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const num = (value, digits = 5) => value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toLocaleString(undefined, {maximumFractionDigits: digits});
  const pct = value => value == null || Number.isNaN(Number(value)) ? '—' : `${Number(value).toFixed(1)}%`;
  const tone = value => { const v = String(value || '').toUpperCase(); return v === 'BUY' ? 'buy' : v === 'SELL' ? 'sell' : 'hold'; };
  const stateText = value => String(value || 'WAITING').replaceAll('_', ' ');
  const S = { rows: [], last: null, scanning: false, scanStartedAt: 0 };

  function setStatus(message, live = false) {
    if ($('signalsFeed')) $('signalsFeed').textContent = message;
    if ($('signalsFeedAge')) $('signalsFeedAge').textContent = live ? 'Fresh authenticated Deriv snapshot' : 'No current live snapshot';
  }

  async function getApiClient() {
    const api = window.AlgoBotAPI?.apiClient;
    if (api) return api;
    await new Promise(resolve => {
      let done = false;
      const finish = () => { if (!done) { done = true; resolve(); } };
      window.addEventListener('algobot:api-ready', finish, {once: true});
      setTimeout(finish, 2500);
    });
    if (window.AlgoBotAPI?.apiClient) return window.AlgoBotAPI.apiClient;
    throw new Error('The AlgoBot API client is still loading. Refresh the page and retry.');
  }

  async function request(path) {
    const api = await getApiClient();
    return api.get(path, {credentials: 'include', timeout: 15000});
  }

  function populateSymbols(rows) {
    const select = $('signalsSymbol');
    if (!select) return;
    const current = select.value;
    const symbols = [...new Map(rows.map(row => [row.symbol, row])).values()];
    select.innerHTML = '<option value="">All instruments</option>' + symbols.map(row => `<option value="${esc(row.symbol)}">${esc(row.symbol)} · ${esc(row.display_name || row.instrument)}</option>`).join('');
    if (symbols.some(row => row.symbol === current)) select.value = current;
  }

  function focus(row) {
    if (!row) {
      $('focusInstrument').textContent = 'Select a market';
      $('focusState').textContent = 'WAITING';
      $('focusState').className = 'signal-state waiting';
      $('focusPrice').textContent = '—';
      $('focusSource').textContent = 'No live tick';
      $('focusConfidence').textContent = '0%';
      $('focusConfidenceBar').style.width = '0%';
      $('focusBaseline').textContent = '—';
      $('focusDirection').textContent = 'HOLD';
      $('focusThreshold').textContent = '—';
      $('focusAge').textContent = '—';
      $('focusEntry').textContent = '—';
      $('focusStop').textContent = '—';
      $('focusTake').textContent = '—';
      $('focusTf').textContent = '—';
      $('focusEvidence').innerHTML = '<span class="muted">No signal selected.</span>';
      return;
    }
    $('focusInstrument').textContent = row.display_name || row.instrument || row.symbol || '—';
    $('focusState').textContent = stateText(row.status);
    $('focusState').className = `signal-state ${tone(row.direction)}${row.status === 'WAITING_FOR_ANALYSIS' ? ' waiting' : ''}`;
    $('focusPrice').textContent = num(row.live?.price);
    $('focusSource').textContent = row.live?.source === 'deriv_authenticated_websocket' ? `Deriv live · ${row.live?.epoch ? new Date(Number(row.live.epoch) * 1000).toLocaleTimeString() : 'now'}` : 'No live tick';
    $('focusConfidence').textContent = pct(row.confidence ?? 0);
    $('focusConfidenceBar').style.width = `${Math.max(0, Math.min(100, Number(row.confidence) || 0))}%`;
    $('focusBaseline').textContent = row.baseline_direction ? `${row.baseline_direction} · ${pct(row.baseline_confidence)}` : 'No Analysis baseline';
    $('focusDirection').textContent = row.direction || 'HOLD';
    $('focusDirection').className = tone(row.direction);
    $('focusThreshold').textContent = pct(row.live_confidence_threshold);
    $('focusAge').textContent = row.live?.age_seconds == null ? '—' : `${row.live.age_seconds}s`;
    $('focusEntry').textContent = num(row.entry_price);
    $('focusStop').textContent = num(row.stop_loss);
    $('focusTake').textContent = num(row.take_profit);
    $('focusTf').textContent = row.timeframe || '—';
    $('focusEvidence').innerHTML = (row.evidence || []).map(item => `<span class="evidence-chip">${esc(stateText(item))}</span>`).join('') || '<span class="muted">No evidence returned.</span>';
  }

  function renderTape(rows) {
    const el = $('liveTape');
    if (!el) return;
    $('marketCount').textContent = `${rows.length} markets`;
    el.innerHTML = rows.slice(0, 20).map(row => `<button type="button" class="tape-row" data-symbol="${esc(row.symbol)}"><span><strong>${esc(row.symbol)}</strong><small>${esc(row.market || 'Deriv')}</small></span><strong>${esc(num(row.live?.price))}</strong><span class="tape-signal ${tone(row.direction)}">${esc(row.direction || 'HOLD')}</span><span>${esc(pct(row.confidence))}</span></button>`).join('') || '<div class="empty">No live market rows returned.</div>';
    el.querySelectorAll('[data-symbol]').forEach(button => button.addEventListener('click', () => focus(S.rows.find(row => row.symbol === button.dataset.symbol))));
  }

  function renderTable(rows) {
    const tbody = $('signalsTable');
    if (!tbody) return;
    tbody.innerHTML = rows.map(row => `<tr data-symbol="${esc(row.symbol)}"><td><strong>${esc(row.display_name || row.symbol)}</strong><small>${esc(row.symbol)}</small></td><td>${esc(row.market || '—')}<small>${esc(row.sub_market || '')}</small></td><td>${esc(row.timeframe || '—')}</td><td>${esc(num(row.live?.price))}</td><td class="${tone(row.baseline_direction)}">${esc(row.baseline_direction || '—')}</td><td class="${tone(row.direction)}">${esc(row.direction || 'HOLD')}</td><td><strong>${esc(pct(row.confidence))}</strong></td><td>${row.live?.age_seconds == null ? '—' : `${esc(row.live.age_seconds)}s`}</td><td><span class="status-pill ${tone(row.direction)}">${esc(stateText(row.status))}</span></td></tr>`).join('') || '<tr><td colspan="9">No live signal data returned.</td></tr>';
    tbody.querySelectorAll('tr[data-symbol]').forEach(row => row.addEventListener('click', () => focus(S.rows.find(item => item.symbol === row.dataset.symbol))));
  }

  function renderHealth(data) {
    const live = Number(data.live_data_available_count || 0);
    const total = Number(data.count || 0);
    const stale = Number(data.stale_count || 0);
    if ($('signalsFeed')) $('signalsFeed').textContent = live === total && total > 0 ? 'LIVE' : live > 0 ? 'PARTIAL' : 'UNAVAILABLE';
    if ($('signalsFeedAge')) $('signalsFeedAge').textContent = live > 0 ? `${live}/${total} live Deriv quotes · ${num(data.feed_latency_ms, 0)} ms` : 'No authenticated Deriv quotes received';
    if ($('signalsReady')) $('signalsReady').textContent = String(data.actionable_count ?? 0);
    if ($('signalsBaseline')) $('signalsBaseline').textContent = `${S.rows.filter(row => row.analysis_signal_id).length}/${S.rows.length} matched`;
    if ($('scanTimestamp')) $('scanTimestamp').textContent = `Scanned ${new Date().toLocaleTimeString()}${stale ? ` · ${stale} stale` : ''}`;
  }

  async function scan() {
    if (S.scanning) return;
    S.scanning = true;
    S.scanStartedAt = performance.now();
    const controls = [$('signalsScan'), $('signalsRefresh')].filter(Boolean);
    controls.forEach(button => { button.disabled = true; button.setAttribute('aria-busy', 'true'); });
    const symbol = $('signalsSymbol')?.value || '';
    const timeframe = $('signalsTimeframe')?.value || 'M1';
    const limit = $('signalsLimit')?.value || '40';
    const path = `/api/strategy-signals/?limit=${encodeURIComponent(limit)}&timeframe=${encodeURIComponent(timeframe)}${symbol ? `&symbol=${encodeURIComponent(symbol)}` : ''}`;
    try {
      setStatus('Authenticating Deriv live feed…');
      const data = await request(path);
      if (data.status !== 'ok') throw new Error(data.message || 'Live signal service returned an invalid response.');
      S.rows = Array.isArray(data.data) ? data.data : [];
      S.last = data;
      populateSymbols(S.rows);
      if ($('signalsAccount')) $('signalsAccount').textContent = data.account?.id || '—';
      if ($('signalsAccountType')) $('signalsAccountType').textContent = `${data.account?.type || 'account'} · ${data.account?.currency || ''}`;
      renderHealth(data);
      setStatus(Number(data.live_data_available_count || 0) > 0 ? 'LIVE' : 'LIVE DATA UNAVAILABLE', Number(data.live_data_available_count || 0) > 0);
      renderTape(S.rows); renderTable(S.rows);
      const preferred = S.rows.find(row => row.execution_ready) || S.rows.find(row => row.direction === 'BUY' || row.direction === 'SELL') || S.rows.find(row => row.live) || S.rows[0];
      focus(preferred);
    } catch (error) {
      S.rows = [];
      const message = error?.message || 'Authenticated Deriv live feed unavailable.';
      setStatus(message);
      if ($('signalsReady')) $('signalsReady').textContent = '0';
      if ($('signalsBaseline')) $('signalsBaseline').textContent = 'Unavailable';
      if ($('scanTimestamp')) $('scanTimestamp').textContent = `Scan failed · ${new Date().toLocaleTimeString()}`;
      renderTape([]); renderTable([]); focus(null);
    } finally {
      S.scanning = false;
      controls.forEach(button => { button.disabled = false; button.removeAttribute('aria-busy'); });
    }
  }

  function boot() {
    $('signalsScan')?.addEventListener('click', scan);
    $('signalsRefresh')?.addEventListener('click', scan);
    $('signalsSymbol')?.addEventListener('change', scan);
    $('signalsTimeframe')?.addEventListener('change', scan);
    $('signalsLimit')?.addEventListener('change', scan);
    window.addEventListener('algobot:account-synced', () => { S.rows = []; setStatus('Account changed — authenticating the new Deriv feed…'); scan(); });
    window.addEventListener('algobot:account-changed', () => { S.rows = []; setStatus('Account changed — authenticating the new Deriv feed…'); scan(); });
    scan();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
