(() => {
  const root = document.querySelector('[data-heatmap-root]');
  if (!root) return;
  const grid = root.querySelector('[data-heatmap-grid]');
  const timeframe = root.querySelector('[data-heatmap-timeframe]');
  const status = root.querySelector('[data-heatmap-status]');
  const refresh = root.querySelector('[data-heatmap-refresh]');

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const score = row => {
    const rsi = Number(row.rsi);
    const confidence = Number(row.confidence);
    const signal = String(row.signal || '').toUpperCase();
    const direction = signal.includes('BEAR') ? -1 : signal.includes('BULL') ? 1 : 0;
    const rsiScore = Number.isFinite(rsi) ? Math.max(-1, Math.min(1, (rsi - 50) / 30)) : 0;
    const confidenceScore = Number.isFinite(confidence) ? Math.max(0, Math.min(1, confidence > 1 ? confidence / 100 : confidence)) : .35;
    return Math.max(-1, Math.min(1, (rsiScore * .55) + (direction * confidenceScore * .45)));
  };
  const background = value => {
    const magnitude = Math.round(Math.abs(value) * 100);
    if (value >= 0) return `linear-gradient(135deg, hsl(150 55% ${Math.max(20, 38 - magnitude * .12)}%), hsl(155 55% ${Math.max(14, 28 - magnitude * .08)}%))`;
    return `linear-gradient(135deg, hsl(350 65% ${Math.max(20, 40 - magnitude * .12)}%), hsl(4 60% ${Math.max(14, 29 - magnitude * .08)}%))`;
  };
  const load = async () => {
    status.textContent = 'Loading…'; status.className = 'ds-status ds-status--pending'; refresh.disabled = true;
    grid.innerHTML = '<div class="hm-empty">Refreshing market intelligence…</div>';
    try {
      const response = await fetch(`/api/market/indicator-dashboard/heatmap/?timeframe=${encodeURIComponent(timeframe.value)}`, {credentials:'same-origin', headers:{Accept:'application/json'}});
      if (!response.ok) throw new Error(`Heatmap request failed (${response.status})`);
      const rows = await response.json();
      if (!Array.isArray(rows) || !rows.length) { grid.innerHTML = '<div class="hm-empty">No active market data is available for this timeframe.</div>'; status.textContent = 'No data'; status.className='ds-status ds-status--degraded'; return; }
      grid.innerHTML = rows.map(row => {
        const value = score(row); const pct = Math.round(Math.abs(value) * 100); const rsi = Number(row.rsi); const confidence = Number(row.confidence);
        return `<article class="hm-cell" style="background:${background(value)}" title="${escapeHtml(row.symbol)} — ${escapeHtml(row.signal || 'Neutral')}"><span class="hm-symbol">${escapeHtml(row.symbol)}</span><span class="hm-value">${value >= 0 ? '+' : ''}${pct}</span><span class="hm-meta"><span>${Number.isFinite(rsi) ? `RSI ${rsi.toFixed(1)}` : 'RSI —'}</span><span>${Number.isFinite(confidence) ? `${Math.round(confidence > 1 ? confidence : confidence * 100)}% conf.` : '—'}</span></span></article>`;
      }).join('');
      status.textContent = `${rows.length} markets`; status.className='ds-status ds-status--ready';
    } catch (error) {
      grid.innerHTML = `<div class="hm-empty"><strong>Heatmap unavailable</strong><br>${escapeHtml(error.message)}<br><button class="ds-btn" type="button" data-heatmap-retry>Retry</button></div>`;
      grid.querySelector('[data-heatmap-retry]').onclick = load; status.textContent='Error'; status.className='ds-status ds-status--danger';
    } finally { refresh.disabled = false; }
  };
  timeframe.addEventListener('change', load); refresh.addEventListener('click', load); load();
})();
