(() => {
  'use strict';
  const root = document.querySelector('[data-analysis-workspace]');
  if (!root || !window.AlgoBotFrontendData) return;
  const list = value => window.AlgoBotFrontendData.list(value);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
  const signals = root.querySelector('[data-analysis-signals]');
  const render = rows => {
    signals.innerHTML = rows.length ? rows.slice(0, 8).map(row => {
      const direction = String(row.direction || '').toUpperCase();
      const action = direction === 'BUY' || direction === 'SELL' ? `<a class="btn small primary" href="/trading/?symbol=${encodeURIComponent(row.symbol || '')}&direction=${direction}&signal_id=${encodeURIComponent(row.id || '')}&strategy=${encodeURIComponent(row.strategy || '')}">Prepare ${direction}</a>` : '';
      return `<div class="mini-row"><strong>${esc(row.symbol || 'Signal')}</strong><span>${esc(row.strategy || direction || 'Backend signal')}</span><b>${esc(row.confidence ?? '—')}% ${action}</b></div>`;
    }).join('') : '<div class="empty-state">No current broker-backed signals are available.</div>';
  };
  const load = async () => {
    try {
      const rows = list(await window.AlgoBotFrontendData.request('/api/strategy-signals/?limit=100', {}, 8000));
      render(rows);
    } catch (_) {
      render([]);
    }
  };
  load();
})();
