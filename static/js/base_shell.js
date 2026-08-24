/* Shared application-shell behavior. Idempotent so page scripts remain safe. */
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
    const labels = {
      NO_BROKER: 'No connected broker account', CONNECTING: 'Connecting broker…', CONNECTED: 'Broker connected',
      SYNCING: 'Synchronizing broker…', READY: 'Broker ready', DEGRADED: 'Broker connection degraded',
      DISCONNECTED: 'Broker disconnected', RECONNECTING: 'Reconnecting broker…', ERROR: 'Broker connection error'
    };
    const account = event?.detail?.state?.account;
    const label = account?.broker?.name && account?.broker_account_id
      ? `${account.broker.name} · ${account.broker_account_id}`
      : labels[status] || 'Broker status unavailable';
    indicator.querySelector('span')?.replaceChildren(document.createTextNode(label));
    indicator.classList.toggle('connected', status === 'CONNECTED' || status === 'READY');
    indicator.classList.toggle('error', status === 'ERROR');
  }

  function bindBrokerState() {
    window.AlgoBotBrokerState?.subscribe(setBrokerStateAttribute);
  }

  function bindNavigation() {
    const sidebar = $('#app-sidebar');
    if (!sidebar || sidebar.dataset.navigationBound === 'true') return;
    sidebar.dataset.navigationBound = 'true';
    const backdrop = $('[data-sidebar-backdrop]');
    const mobile = $('[data-mobile-menu]');
    const toggle = $('[data-sidebar-toggle]');
    const shell = $('.app-shell');

    const closeMobile = () => {
      sidebar.classList.remove('is-open');
      if (backdrop) backdrop.hidden = true;
      mobile?.setAttribute('aria-expanded', 'false');
    };
    const openMobile = () => {
      sidebar.classList.add('is-open');
      if (backdrop) backdrop.hidden = false;
      mobile?.setAttribute('aria-expanded', 'true');
    };

    mobile?.addEventListener('click', () => sidebar.classList.contains('is-open') ? closeMobile() : openMobile());
    backdrop?.addEventListener('click', closeMobile);
    sidebar.querySelectorAll('nav a, .sidebar-new-trade').forEach(link => link.addEventListener('click', closeMobile));

    if (toggle) {
      const setCollapsed = collapsed => {
        sidebar.classList.toggle('is-collapsed', collapsed);
        shell?.classList.toggle('sidebar-collapsed', collapsed);
        document.body.classList.toggle('sidebar-collapsed', collapsed);
        toggle.setAttribute('aria-expanded', String(!collapsed));
        toggle.setAttribute('aria-label', collapsed ? 'Expand navigation' : 'Collapse navigation');
        toggle.querySelector('.material-symbols-rounded')?.replaceChildren(document.createTextNode(collapsed ? 'left_panel_open' : 'left_panel_close'));
      };
      toggle.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        setCollapsed(!sidebar.classList.contains('is-collapsed'));
      });
    }
  }

  function bindTheme() {
    const button = $('[data-theme-toggle]');
    if (!button || button.dataset.themeBound === 'true') return;
    button.dataset.themeBound = 'true';
    const storageKey = 'algobot-theme';
    const apply = theme => {
      document.documentElement.dataset.theme = theme;
      button.setAttribute('aria-pressed', String(theme === 'light'));
    };
    const stored = localStorage.getItem(storageKey);
    if (stored === 'light' || stored === 'dark') apply(stored);
    button.addEventListener('click', () => {
      const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      localStorage.setItem(storageKey, next);
      apply(next);
    });
  }

  function boot() {
    bindNavigation();
    bindTheme();
    bindBrokerState();
    document.querySelectorAll('.toast-stack .toast').forEach(node => setTimeout(() => node.remove(), 4500));
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
