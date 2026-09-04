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

  function injectStyles() {
    if ($('#terminal-strategy-switcher-styles')) return;
    const style = document.createElement('style');
    style.id = 'terminal-strategy-switcher-styles';
    style.textContent = `
      .strategy-switch-trigger{display:inline-flex;align-items:center;gap:.55rem;margin-top:.7rem;padding:.65rem .9rem;border:1px solid rgba(88,214,170,.32);border-radius:12px;background:rgba(88,214,170,.07);color:inherit;cursor:pointer;font:inherit}
      .strategy-switch-trigger:hover{background:rgba(88,214,170,.13);border-color:rgba(88,214,170,.55)}
      .strategy-switch-modal{position:fixed;inset:0;z-index:10000;display:grid;place-items:center;padding:18px;background:rgba(3,7,13,.78);backdrop-filter:blur(10px)}
      .strategy-switch-modal[hidden]{display:none}
      .strategy-switch-dialog{width:min(760px,calc(100vw - 28px));max-height:min(760px,calc(100vh - 32px));overflow:hidden;display:flex;flex-direction:column;border:1px solid rgba(117,142,174,.3);border-radius:24px;background:#171b22;box-shadow:0 24px 80px rgba(0,0,0,.55)}
      .strategy-switch-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:22px 22px 16px;border-bottom:1px solid rgba(117,142,174,.18)}
      .strategy-switch-head h2{margin:.25rem 0 0;font-size:1.45rem}.strategy-switch-head p{margin:.35rem 0 0;color:#98a8bf}
      .strategy-switch-close{width:38px;height:38px;border:0;border-radius:12px;background:#242a34;color:#dce5f2;font-size:24px;cursor:pointer}
      .strategy-switch-toolbar{padding:14px 22px}.strategy-switch-search{width:100%;box-sizing:border-box;padding:12px 14px;border:1px solid rgba(117,142,174,.25);border-radius:12px;background:#10141a;color:#eef4ff;font:inherit}
      .strategy-switch-list{padding:0 22px 22px;overflow:auto;display:grid;gap:10px}
      .strategy-switch-card{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;padding:15px;border:1px solid rgba(117,142,174,.2);border-radius:16px;background:#1d222b}
      .strategy-switch-card:hover{border-color:rgba(88,214,170,.5)}
      .strategy-switch-card.current{border-color:rgba(88,214,170,.72);box-shadow:inset 0 0 0 1px rgba(88,214,170,.14)}
      .strategy-switch-meta{display:flex;flex-wrap:wrap;gap:7px;margin-top:7px}.strategy-switch-pill{font-size:.72rem;padding:4px 7px;border-radius:999px;background:#272e39;color:#aebbd0}.strategy-switch-pill.live{color:#78e1b7;background:rgba(88,214,170,.1)}
      .strategy-switch-select{min-width:104px;padding:10px 12px;border:1px solid rgba(117,142,174,.28);border-radius:10px;background:#252b35;color:#eef4ff;cursor:pointer;font-weight:700}
      .strategy-switch-footer{padding:13px 22px;border-top:1px solid rgba(117,142,174,.18);color:#8494aa;font-size:.82rem}
      @media(max-width:600px){.strategy-switch-dialog{border-radius:18px}.strategy-switch-head{padding:17px}.strategy-switch-toolbar{padding:12px 17px}.strategy-switch-list{padding:0 17px 17px}.strategy-switch-card{grid-template-columns:1fr}.strategy-switch-select{width:100%}}
    `;
    document.head.appendChild(style);
  }

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
    injectStyles();
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