/* Trading terminal strategy selector: switching strategy is state-only and never executes. */
(() => {
  'use strict';
  if (window.__algoBotTerminalStrategySwitcher) return;
  window.__algoBotTerminalStrategySwitcher = true;

  const $ = (s, r = document) => r.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[c]));
  const list = v => window.AlgoBotFrontendData?.list?.(v) || (Array.isArray(v) ? v : []);
  const api = (url, options = {}, timeout = 10000) => window.AlgoBotFrontendData?.request?.(url, options, timeout);
  let strategies = [];
  let modal = null;

  function currentStrategy() { return String($('[name="strategy"]')?.value || '').trim(); }
  function updateUrl(strategy) {
    try {
      const url = new URL(location.href);
      if (strategy) url.searchParams.set('strategy', strategy);
      else url.searchParams.delete('strategy');
      history.replaceState(history.state, '', url.toString());
    } catch (_) {}
  }

  function setStrategy(strategy) {
    const value = String(strategy || '').trim();
    const hidden = $('[name="strategy"]');
    const banner = $('[data-selected-strategy] strong');
    if (hidden) hidden.value = value;
    if (banner) banner.textContent = value || 'Manual trading';
    updateUrl(value);
    window.__algobotTerminalSelectedStrategy = value;
    window.dispatchEvent(new CustomEvent('algobot:terminal-strategy-selected', {detail:{strategy:value, manual:!value}}));
    closeModal();
    const result = $('[data-order-result]');
    if (result) {
      result.hidden = false;
      result.dataset.state = 'info';
      result.textContent = value ? `Strategy selected: ${value}. Strategy automation is controlled by the strategy engine; no order was submitted.` : 'Manual trading selected. Orders are submitted only after you press BUY or SELL.';
    }
  }

  function render(filter = '') {
    if (!modal) return;
    const root = $('.strategy-switch-list', modal);
    const q = String(filter || '').trim().toLowerCase();
    const active = currentStrategy();
    const visible = strategies.filter(s => String(s.name || s.slug || '').toLowerCase().includes(q));
    root.innerHTML = `<article class="strategy-switch-card ${active ? '' : 'current'}"><div><strong>Manual trading</strong><div class="strategy-switch-meta"><span class="strategy-switch-pill live">USER DRIVEN</span><span class="strategy-switch-pill">No automatic orders</span></div></div><button class="strategy-switch-select" type="button" data-select-strategy="">${active ? 'Select' : 'Selected'}</button></article>` +
      (visible.length ? visible.map(s => {
        const id = String(s.slug || s.name || '').trim();
        const name = String(s.name || s.slug || 'Strategy');
        const selected = id === active || name === active;
        return `<article class="strategy-switch-card ${selected ? 'current' : ''}"><div><strong>${esc(name)}</strong><div class="strategy-switch-meta"><span class="strategy-switch-pill">${esc(s.category || 'Strategy')}</span><span class="strategy-switch-pill">v${esc(s.version || '1.0.0')}</span><span class="strategy-switch-pill ${s.enabled ? 'live' : ''}">${s.enabled ? 'Enabled' : 'Disabled'}</span><span class="strategy-switch-pill">${esc(s.lifecycle_state || 'created')}</span></div></div><button class="strategy-switch-select" type="button" data-select-strategy="${esc(id)}">${selected ? 'Selected' : 'Select'}</button></article>`;
      }).join('') : '<div class="empty-state">No strategies match this search.</div>');
    root.querySelectorAll('[data-select-strategy]').forEach(button => button.addEventListener('click', () => setStrategy(button.dataset.selectStrategy || '')));
  }

  function openModal() {
    if (!modal) return;
    modal.hidden = false;
    document.body.style.overflow = 'hidden';
    $('[data-strategy-switch-search]', modal)?.focus();
    loadStrategies();
  }
  function closeModal() {
    if (!modal) return;
    modal.hidden = true;
    document.body.style.overflow = '';
  }

  async function loadStrategies() {
    const root = $('.strategy-switch-list', modal);
    root.innerHTML = '<div class="empty-state">Loading strategy registry…</div>';
    try {
      const data = await api('/api/strategies/', {}, 10000);
      strategies = list(data).filter(s => s && (s.slug || s.name));
      render($('[data-strategy-switch-search]', modal)?.value || '');
    } catch (error) {
      root.innerHTML = `<div class="empty-state">Strategy registry unavailable: ${esc(error?.message || 'request failed')}<br><br>Manual trading remains available and no order was submitted.</div>`;
    }
  }

  function createModal() {
    modal = document.createElement('div');
    modal.className = 'strategy-switch-modal';
    modal.hidden = true;
    modal.setAttribute('role', 'presentation');
    modal.innerHTML = `<section class="strategy-switch-dialog" role="dialog" aria-modal="true" aria-labelledby="strategy-switch-title"><header class="strategy-switch-head"><div><p class="eyebrow">EXECUTION PROFILE</p><h2 id="strategy-switch-title">Choose trading mode</h2><p>Switch strategies without reloading the terminal or submitting an order.</p></div><button class="strategy-switch-close" type="button" data-strategy-switch-close aria-label="Close">×</button></header><div class="strategy-switch-toolbar"><input class="strategy-switch-search" data-strategy-switch-search type="search" placeholder="Search strategies…" aria-label="Search strategies"></div><div class="strategy-switch-list"></div><footer class="strategy-switch-footer">Manual trading is always user-driven. Strategy selection only changes the execution profile; automatic execution belongs to the strategy engine.</footer></section>`;
    document.body.appendChild(modal);
    $('[data-strategy-switch-close]', modal).addEventListener('click', closeModal);
    modal.addEventListener('click', event => { if (event.target === modal) closeModal(); });
    $('[data-strategy-switch-search]', modal).addEventListener('input', event => render(event.target.value));
    document.addEventListener('keydown', event => { if (!modal.hidden && event.key === 'Escape') closeModal(); });
  }

  function bindTrigger() {
    const banner = $('[data-selected-strategy]');
    if (!banner || banner.dataset.strategySwitcherBound) return;
    banner.dataset.strategySwitcherBound = '1';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'strategy-switch-trigger';
    button.textContent = 'Switch strategy';
    button.addEventListener('click', openModal);
    banner.appendChild(button);
  }

  function boot() {
    if (!$('.terminal-page')) return;
    createModal();
    bindTrigger();
    const initial = currentStrategy();
    window.__algobotTerminalSelectedStrategy = initial;
    render();
    window.addEventListener('algobot:account-synced', () => { if (!modal?.hidden) loadStrategies(); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true});
  else boot();
})();