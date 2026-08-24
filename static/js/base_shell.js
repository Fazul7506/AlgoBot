/* Shared application-shell behavior. Navigation owns sidebar state. */
(() => {
  'use strict';
  if (window.__algoBotBaseShell) return;
  window.__algoBotBaseShell = true;

  const $ = (selector, root = document) => root.querySelector(selector);

  function setBrokerStateAttribute(event) {
    const status = event?.detail?.state?.status || window.AlgoBotBrokerState?.get()?.status || 'NO_BROKER';
    document.body.dataset.brokerState = status;
    const indicator = $('[data-global-connection]');
    if (!indicator) return;
    const labels = {NO_BROKER:'No connected broker account',CONNECTING:'Connecting broker…',CONNECTED:'Broker connected',SYNCING:'Synchronizing broker…',READY:'Broker ready',DEGRADED:'Broker connection degraded',DISCONNECTED:'Broker disconnected',RECONNECTING:'Reconnecting broker…',ERROR:'Broker connection error'};
    const account = event?.detail?.state?.account || window.AlgoBotBrokerState?.get()?.account;
    const label = account?.broker?.name && account?.broker_account_id ? `${account.broker.name} · ${account.broker_account_id}` : labels[status] || 'Broker status unavailable';
    indicator.querySelector('span')?.replaceChildren(document.createTextNode(label));
    indicator.classList.toggle('connected', status === 'CONNECTED' || status === 'READY');
    indicator.classList.toggle('error', status === 'ERROR' || status === 'DISCONNECTED');
  }

  function bindNavigation() {
    const sidebar = $('#app-sidebar');
    if (!sidebar || sidebar.dataset.navigationBound === 'true') return;
    sidebar.dataset.navigationBound = 'true';
    const backdrop = $('[data-sidebar-backdrop]');
    const mobile = $('[data-mobile-menu]');
    const toggle = $('[data-sidebar-toggle]');
    const shell = $('.app-shell');
    const storageKey = 'algobot.sidebar.collapsed';

    const setMobileOpen = open => {
      sidebar.classList.toggle('is-open', !!open);
      if (backdrop) backdrop.hidden = !open;
      mobile?.setAttribute('aria-expanded', String(!!open));
      mobile?.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
      document.body.classList.remove('mobile-nav-open');
      document.documentElement.classList.remove('mobile-nav-open');
      // Never lock the document. The fixed sidebar has its own scroll container.
    };

    setMobileOpen(false);

    // Capture-phase pointer handling is deliberately the single source of truth.
    // It runs before page widgets can stop propagation and does not wait for click.
    const handlePointer = event => {
      const target = event.target?.closest?.('[data-mobile-menu]');
      if (target) {
        event.preventDefault();
        setMobileOpen(!sidebar.classList.contains('is-open'));
        return;
      }
      if (backdrop && event.target === backdrop) {
        event.preventDefault();
        setMobileOpen(false);
        return;
      }
      if (sidebar.classList.contains('is-open') && event.target?.closest?.('#app-sidebar nav a, #app-sidebar .sidebar-new-trade')) {
        setMobileOpen(false);
      }
    };
    document.addEventListener('pointerup', handlePointer, true);
    document.addEventListener('click', handlePointer, true);

    if (toggle) {
      const setCollapsed = collapsed => {
        if (window.innerWidth <= 800) return;
        sidebar.classList.toggle('is-collapsed', !!collapsed);
        shell?.classList.toggle('sidebar-collapsed', !!collapsed);
        document.body.classList.toggle('sidebar-collapsed', !!collapsed);
        toggle.setAttribute('aria-expanded', String(!collapsed));
        toggle.setAttribute('aria-label', collapsed ? 'Expand navigation' : 'Collapse navigation');
        const icon = toggle.querySelector('.material-symbols-rounded');
        if (icon) icon.textContent = collapsed ? 'left_panel_open' : 'left_panel_close';
        try { localStorage.setItem(storageKey, collapsed ? '1' : '0'); } catch (_) {}
      };
      try { if (window.innerWidth > 800 && localStorage.getItem(storageKey) === '1') setCollapsed(true); } catch (_) {}
      toggle.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        setCollapsed(!sidebar.classList.contains('is-collapsed'));
      });
    }

    document.addEventListener('keydown', event => { if (event.key === 'Escape') setMobileOpen(false); });
    window.addEventListener('resize', () => { if (window.innerWidth > 800) setMobileOpen(false); });
  }

  function bindTheme() {
    const button = $('[data-theme-toggle]');
    if (!button || button.dataset.themeBound === 'true') return;
    button.dataset.themeBound = 'true';
    const storageKey = 'algobot-theme';
    const apply = theme => { document.documentElement.dataset.theme = theme; button.setAttribute('aria-pressed', String(theme === 'light')); };
    let stored = null; try { stored = localStorage.getItem(storageKey); } catch (_) {}
    if (stored === 'light' || stored === 'dark') apply(stored);
    button.addEventListener('click', () => { const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; try { localStorage.setItem(storageKey, next); } catch (_) {} apply(next); });
  }

  function boot() { bindNavigation(); bindTheme(); window.AlgoBotBrokerState?.subscribe(setBrokerStateAttribute); document.querySelectorAll('.toast-stack .toast').forEach(node => setTimeout(() => node.remove(), 4500)); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true }); else boot();
})();
