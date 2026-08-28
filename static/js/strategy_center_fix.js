(() => {
  'use strict';
  if (window.__algoBotStrategyCenterFix) return;
  window.__algoBotStrategyCenterFix = true;

  const $ = s => document.querySelector(s);
  const list = v => Array.isArray(v) ? v : (v?.results || v?.data || v?.items || []);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const tradeUrl = s => `/trading/?strategy=${encodeURIComponent(s.slug || s.name || '')}`;
  let strategies = [];

  function renderList() {
    const q = String($('[data-s-search]')?.value || '').trim().toLowerCase();
    const visible = strategies.filter(s => String(s.name || s.slug || '').toLowerCase().includes(q));
    $('[data-s-total]').textContent = strategies.length;
    $('[data-s-enabled]').textContent = strategies.filter(s => s.enabled).length;
    $('[data-s-running]').textContent = strategies.filter(s => ['running','active'].includes(String(s.lifecycle_state || '').toLowerCase())).length;
    $('[data-s-list]').innerHTML = visible.length ? visible.map(s => `<article class="strategy-row"><div><strong>${esc(s.name || s.slug || 'Strategy')}</strong><small>${esc(s.category || 'Strategy')} · v${esc(s.version || '1.0.0')}</small></div><span class="state-badge">${esc(s.lifecycle_state || 'created')}</span><span>${s.enabled ? 'Enabled' : 'Disabled'}</span><a class="btn small ghost" href="${tradeUrl(s)}">Trade</a></article>`).join('') : '<div class="empty-state">No strategies are registered for this account yet.</div>';
  }

  async function load() {
    const data = window.AlgoBotFrontendData;
    if (!data?.request) return;
    $('[data-s-list]').innerHTML = '<div class="empty-state">Loading strategy registry…</div>';
    try {
      const [sr, sig, perf] = await Promise.allSettled([
        data.request('/api/strategies/'),
        data.request('/api/strategies/signals/'),
        data.request('/api/strategies/performance/')
      ]);
      if (sr.status === 'rejected') throw sr.reason;
      strategies = list(sr.value);
      renderList();
      const signals = sig.status === 'fulfilled' ? list(sig.value) : [];
      const performance = perf.status === 'fulfilled' ? list(perf.value) : [];
      $('[data-s-strategy-signals]').innerHTML = signals.length ? signals.slice(0,8).map(s => `<div class="signal-row"><strong>${esc(s.symbol || '—')}</strong><span>${esc(s.signal || 'HOLD')}</span><b>${s.confidence != null ? Number(s.confidence).toFixed(0) + '%' : '—'}</b></div>`).join('') : '<div class="empty-state">No strategy signals have been generated yet.</div>';
      $('[data-s-performance]').innerHTML = performance.length ? performance.slice(0,8).map(p => `<div class="mini-row"><strong>${esc(p.strategy_name || p.strategy || 'Strategy')}</strong><span>${p.win_rate != null ? Number(p.win_rate).toFixed(1) + '%' : '—'}</span><b>${esc(p.net_profit ?? '0')}</b></div>`).join('') : '<div class="empty-state">No strategy performance records yet.</div>';
      $('[data-s-strategy-signals]').closest('.panel')?.setAttribute('data-broker-state', window.AlgoBotBrokerState?.get()?.status || 'UNKNOWN');
    } catch (e) {
      const msg = esc(e?.message || 'Unable to load strategy data.');
      $('[data-s-list]').innerHTML = `<div class="empty-state">Strategy registry unavailable: ${msg} <button class="btn small ghost" type="button" data-s-retry>Retry</button></div>`;
      $('[data-s-strategy-signals]').innerHTML = '<div class="empty-state">Strategy signals unavailable.</div>';
      $('[data-s-performance]').innerHTML = '<div class="empty-state">Strategy performance unavailable.</div>';
      ['[data-s-total]','[data-s-enabled]','[data-s-running]','[data-s-signals]'].forEach(s => { const n=$(s); if(n) n.textContent='—'; });
      $('[data-s-retry]')?.addEventListener('click', load, {once:true});
    }
  }

  async function action(path) {
    try {
      window.AlgoBotFrontendData.requireConnected('run or change executable strategies');
      const result = await window.AlgoBotFrontendData.request(path, {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      window.alert(result?.detail || 'Strategy action completed.');
      load();
    } catch(e) { window.alert(e?.message || 'Strategy action failed.'); }
  }

  function boot() {
    document.querySelectorAll('[data-strategy-run]').forEach(b => b.addEventListener('click', () => action('/api/strategies/run/')));
    $('[data-strategy-pause]')?.addEventListener('click', () => action('/api/strategies/pause/'));
    $('[data-strategy-stop]')?.addEventListener('click', () => { if(confirm('Stop all active strategies for this account?')) action('/api/strategies/stop/'); });
    $('[data-s-search]')?.addEventListener('input', renderList);
    window.AlgoBotBrokerState?.subscribe(() => load());
    load();
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true}); else boot();
})();