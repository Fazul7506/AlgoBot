(() => {
  'use strict';
  if (window.__algoBotLiveSignalsPage) return;
  window.__algoBotLiveSignalsPage = true;

  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const num = (value, digits = 5) => value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toLocaleString(undefined, {maximumFractionDigits: digits});
  const pct = value => value == null || Number.isNaN(Number(value)) ? '—' : `${Number(value).toFixed(1)}%`;
  const tone = value => {
    const v = String(value || '').toUpperCase();
    return v === 'BUY' ? 'buy' : v === 'SELL' ? 'sell' : 'hold';
  };
  const stateText = value => String(value || 'WAITING').replaceAll('_', ' ');

  const S = { rows: [], last: null };

  async function request(path) {
    const api = window.AlgoBotAPI?.apiClient;
    if (!api) throw new Error('Canonical API client is not available.');
    return api.get(path, {credentials: 'include', timeout: 30000});
  }

  function setStatus(message, live = false) {
    const feed = $('signalsFeed');
    if (feed) feed.textContent = message;
    if ($('signalsFeedAge')) $('signalsFeedAge').textContent = live ? 'Fresh Deriv snapshot' : 'No current live snapshot';
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
    if (!row) return;
    $('focusInstrument').textContent = row.display_name || row.instrument || row.symbol || '—';
    $('focusState').textContent = stateText(row.status);
    $('focusState').className = `signal-state ${tone(row.direction)}`;
    $('focusPrice').textContent = num(row.live?.price);
    $('focusSource').textContent = row.live?.source === 'deriv_authenticated_websocket' ? `Deriv live · ${row.live?.epoch ? new Date(Number(row.live.epoch) * 1000).toLocaleTimeString() : 'now'}` : 'No live tick';
    $('focusConfidence').textContent = pct(row.confidence);
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
    el.innerHTML = rows.slice(0, 20).map(row => `<button class="tape-row" data-symbol="${esc(row.symbol)}"><span><strong>${esc(row.symbol)}</strong><small>${esc(row.market || 'Deriv')}</small></span><strong>${esc(num(row.live?.price))}</strong><span class="tape-signal ${tone(row.direction)}">${esc(row.direction || 'HOLD')}</span><span>${esc(pct(row.confidence))}</span></button>`).join('') || '<div class="empty">No live market rows returned.</div>';
    el.querySelectorAll('[data-symbol]').forEach(button => button.addEventListener('click', () => focus(S.rows.find(row => row.symbol === button.dataset.symbol))));
  }

  function renderTable(rows) {
    const tbody = $('signalsTable');
    if (!tbody) return;
    tbody.innerHTML = rows.map(row => `<tr data-symbol="${esc(row.symbol)}"><td><strong>${esc(row.display_name || row.symbol)}</strong><small>${esc(row.symbol)}</small></td><td>${esc(row.market || '—')}<small>${esc(row.sub_market || '')}</small></td><td>${esc(row.timeframe || '—')}</td><td>${esc(num(row.live?.price))}</td><td class="${tone(row.baseline_direction)}">${esc(row.baseline_direction || '—')}</td><td class="${tone(row.direction)}">${esc(row.direction || 'HOLD')}</td><td><strong>${esc(pct(row.confidence))}</strong></td><td>${row.live?.age_seconds == null ? '—' : `${esc(row.live.age_seconds)}s`}</td><td><span class="status-pill ${tone(row.direction)}">${esc(stateText(row.status))}</span></td></tr>`).join('') || '<tr><td colspan="9">No live signal data returned.</td></tr>';
    tbody.querySelectorAll('tr[data-symbol]').forEach(row => row.addEventListener('click', () => focus(S.rows.find(item => item.symbol === row.dataset.symbol))));
  }

  async function scan() {
    const symbol = $('signalsSymbol').value;
    const timeframe = $('signalsTimeframe').value;
    const limit = $('signalsLimit').value;
    const path = `/api/strategy-signals/?limit=${encodeURIComponent(limit)}&timeframe=${encodeURIComponent(timeframe)}${symbol ? `&symbol=${encodeURIComponent(symbol)}` : ''}`;
    try {
      setStatus('Reading Deriv…');
      const data = await request(path);
      S.rows = Array.isArray(data.data) ? data.data : [];
      S.last = data;
      populateSymbols(S.rows);
      $('signalsAccount').textContent = data.account?.id || '—';
      $('signalsAccountType').textContent = `${data.account?.type || 'account'} · ${data.account?.currency || ''}`;
      $('signalsReady').textContent = String(data.actionable_count ?? S.rows.filter(row => row.execution_ready).length);
      $('signalsBaseline').textContent = `${S.rows.filter(row => row.analysis_signal_id).length}/${S.rows.length} matched`;
      setStatus('LIVE', true);
      $('scanTimestamp').textContent = `Scanned ${new Date().toLocaleTimeString()}`;
      renderTape(S.rows); renderTable(S.rows);
      const preferred = S.rows.find(row => row.execution_ready) || S.rows.find(row => row.direction === 'BUY' || row.direction === 'SELL') || S.rows[0];
      focus(preferred);
    } catch (error) {
      S.rows = [];
      setStatus(error.message || 'Live feed unavailable');
      $('signalsReady').textContent = '0';
      $('signalsBaseline').textContent = 'Unavailable';
      renderTape([]); renderTable([]);
    }
  }

  function boot() {
    $('signalsScan')?.addEventListener('click', scan);
    $('signalsRefresh')?.addEventListener('click', scan);
    $('signalsSymbol')?.addEventListener('change', scan);
    $('signalsTimeframe')?.addEventListener('change', scan);
    $('signalsLimit')?.addEventListener('change', scan);
    window.addEventListener('algobot:account-synced', () => { S.rows = []; setStatus('Account changed — run live scan'); });
    // Deliberately no timer: live Signals is a user-triggered authenticated snapshot,
    // while continuous Deriv streams belong to the trading/market-data websocket layer.
    scan();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
