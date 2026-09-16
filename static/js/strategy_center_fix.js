(() => {
  'use strict';
  if (window.__algoBotStrategyCenterFix) return;
  window.__algoBotStrategyCenterFix = true;

  const $ = s => document.querySelector(s);
  const list = v => Array.isArray(v) ? v : (v?.results || v?.data || v?.items || []);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const tradeUrl = s => `/trading/?strategy=${encodeURIComponent(s.slug || s.name || '')}`;
  const builderUrl = s => `/strategies/builder/?strategy=${encodeURIComponent(s.slug || '')}`;
  let strategies = [];

  function counts(data, signals) {
    $('[data-s-total]').textContent = strategies.length;
    $('[data-s-enabled]').textContent = Number.isFinite(Number(data?.configured_count)) ? Number(data.configured_count) : strategies.filter(s => s.configured).length;
    $('[data-s-running]').textContent = Number.isFinite(Number(data?.running_count)) ? Number(data.running_count) : strategies.filter(s => s.running).length;
    $('[data-s-signals]').textContent = signals.length;
  }

  function renderList() {
    const q = String($('[data-s-search]')?.value || '').trim().toLowerCase();
    const visible = strategies.filter(s => String(s.name || s.slug || '').toLowerCase().includes(q));
    $('[data-s-list]').innerHTML = visible.length ? visible.map(s => {
      const configs = Array.isArray(s.configurations) ? s.configurations : [];
      const active = s.active_configuration || configs.find(c => c.is_active && c.enabled);
      const state = s.running ? 'RUNNING' : (s.configured ? 'CONFIGURED' : 'AVAILABLE');
      const stateClass = s.running ? 'active' : (s.configured ? 'configured' : 'available');
      const detail = active ? `${esc(active.symbol || '—')} · ${esc(active.timeframe || '—')}` : (s.configured ? `${configs.length} saved configuration${configs.length === 1 ? '' : 's'}` : 'Not configured');
      const action = s.running
        ? `<button class="btn small ghost" type="button" data-strategy-disconnect data-strategy-id="${esc(s.id)}" data-config-id="${esc(active?.id || '')}">Disconnect</button>`
        : s.configured
          ? `<button class="btn small primary" type="button" data-strategy-switch data-strategy-id="${esc(s.id)}" data-config-id="${esc((configs.find(c => c.enabled) || configs[0])?.id || '')}">Use strategy</button>`
          : `<a class="btn small ghost" href="${builderUrl(s)}">Configure</a>`;
      return `<article class="strategy-row strategy-control-row"><div class="strategy-row-main"><strong>${esc(s.name || s.slug || 'Strategy')}</strong><small>${esc(s.category || 'Strategy')} · v${esc(s.version || '1.0.0')}</small><small class="strategy-config-detail">${detail}</small></div><span class="state-badge ${stateClass}">${state}</span><div class="strategy-actions-inline">${action}<a class="btn small ghost" href="${tradeUrl(s)}">Trade</a></div></article>`;
    }).join('') : '<div class="empty-state">No strategies match your search.</div>';
  }

  async function load() {
    const data = window.AlgoBotFrontendData;
    if (!data?.request) return;
    $('[data-s-list]').innerHTML = '<div class="empty-state">Loading strategy control plane…</div>';
    try {
      const [sr, sig, perf] = await Promise.allSettled([
        data.request('/api/strategies/available/'),
        data.request('/api/strategies/signals/'),
        data.request('/api/strategies/performance/')
      ]);
      if (sr.status === 'rejected') throw sr.reason;
      const payload = sr.value || {};
      strategies = list(payload.strategies || payload);
      const signals = sig.status === 'fulfilled' ? list(sig.value) : [];
      const performance = perf.status === 'fulfilled' ? list(perf.value) : [];
      counts(payload, signals);
      renderList();
      $('[data-s-strategy-signals]').innerHTML = signals.length ? signals.slice(0,8).map(s => `<div class="signal-row"><strong>${esc(s.symbol || '—')}</strong><span>${esc(s.signal || 'HOLD')}</span><b>${s.confidence != null ? Number(s.confidence).toFixed(0) + '%' : '—'}</b></div>`).join('') : '<div class="empty-state">No strategy signals have been generated yet.</div>';
      $('[data-s-performance]').innerHTML = performance.length ? performance.slice(0,8).map(p => `<div class="mini-row"><strong>${esc(p.strategy_name || p.strategy || 'Strategy')}</strong><span>${p.win_rate != null ? Number(p.win_rate).toFixed(1) + '%' : '—'}</span><b>${esc(p.net_profit ?? '0')}</b></div>`).join('') : '<div class="empty-state">No strategy performance records yet.</div>';
    } catch (e) {
      const msg = esc(e?.message || 'Unable to load strategy data.');
      $('[data-s-list]').innerHTML = `<div class="empty-state">Strategy control plane unavailable: ${msg} <button class="btn small ghost" type="button" data-s-retry>Retry</button></div>`;
      $('[data-s-strategy-signals]').innerHTML = '<div class="empty-state">Strategy signals unavailable.</div>';
      $('[data-s-performance]').innerHTML = '<div class="empty-state">Strategy performance unavailable.</div>';
      ['[data-s-total]','[data-s-enabled]','[data-s-running]','[data-s-signals]'].forEach(s => { const n=$(s); if(n) n.textContent='—'; });
      $('[data-s-retry]')?.addEventListener('click', load, {once:true});
    }
  }

  async function post(path, body, successMessage) {
    const data = window.AlgoBotFrontendData;
    if (!data?.request) throw new Error('Strategy service is not ready.');
    const result = await data.request(path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body || {})});
    if (result?.detail && result?.status === 'error') throw new Error(result.detail);
    window.alert(result?.message || result?.detail || successMessage);
    await load();
  }

  async function useStrategy(id, configId) {
    try { await post(`/api/strategies/${encodeURIComponent(id)}/switch/`, configId ? {configuration_id: Number(configId)} : {}, 'Strategy is now the active configured strategy.'); }
    catch(e) { window.alert(e?.message || 'Unable to switch strategy.'); }
  }

  async function disconnectStrategy(id, configId) {
    try { await post(`/api/strategies/${encodeURIComponent(id)}/disconnect/`, configId ? {configuration_id: Number(configId)} : {}, 'Strategy disconnected. Its configuration was preserved.'); }
    catch(e) { window.alert(e?.message || 'Unable to disconnect strategy.'); }
  }

  async function action(path) {
    try {
      window.AlgoBotFrontendData.requireConnected('run or change executable strategies');
      const result = await window.AlgoBotFrontendData.request(path, {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      window.alert(result?.detail || 'Strategy action completed.');
      await load();
    } catch(e) { window.alert(e?.message || 'Strategy action failed.'); }
  }

  function boot() {
    document.querySelectorAll('[data-strategy-run]').forEach(b => b.addEventListener('click', () => action('/api/strategies/run/')));
    $('[data-strategy-pause]')?.addEventListener('click', () => action('/api/strategies/pause/'));
    $('[data-strategy-stop]')?.addEventListener('click', () => { if(confirm('Stop all active strategies for this account?')) action('/api/strategies/stop/'); });
    $('[data-s-search]')?.addEventListener('input', renderList);
    $('[data-s-list]')?.addEventListener('click', e => {
      const switchButton = e.target.closest('[data-strategy-switch]');
      if (switchButton) useStrategy(switchButton.dataset.strategyId, switchButton.dataset.configId);
      const disconnectButton = e.target.closest('[data-strategy-disconnect]');
      if (disconnectButton && confirm('Disconnect this strategy? Its saved configuration will remain available for later use.')) disconnectStrategy(disconnectButton.dataset.strategyId, disconnectButton.dataset.configId);
    });
    load();
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true}); else boot();
})();