/* Canonical application-shell navigation and Django-message notification UI. */
(() => {
  'use strict';
  if (window.__algoBotBaseShell) return;
  window.__algoBotBaseShell = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const stack = () => $('#django-message-stack');
  const MESSAGE_LIMIT = 5;
  const MESSAGE_TTL = 5000;

  function setBrokerStateAttribute(event) {
    const state = event?.detail?.state || window.AlgoBotBrokerState?.get() || {};
    const status = state.status || 'NO_BROKER';
    document.body.dataset.brokerState = status;
    const indicator = $('[data-global-connection]');
    if (!indicator) return;
    const labels = {
      NO_BROKER: 'No connected broker account', CONNECTING: 'Connecting broker…',
      CONNECTED: 'Broker connected', SYNCING: 'Synchronizing broker…', READY: 'Broker ready',
      DEGRADED: 'Broker connection degraded', DISCONNECTED: 'Broker disconnected',
      RECONNECTING: 'Reconnecting broker…', ERROR: 'Broker connection error',
    };
    const account = state.account;
    const label = account?.broker?.name && account?.broker_account_id
      ? `${account.broker.name} · ${account.broker_account_id}`
      : labels[status] || 'Broker status unavailable';
    const span = indicator.querySelector('span');
    if (span) span.textContent = label;
    indicator.classList.toggle('connected', status === 'CONNECTED' || status === 'READY');
    indicator.classList.toggle('error', status === 'ERROR' || status === 'DISCONNECTED');
  }

  function removeToast(node) {
    if (!node || node.dataset.removing === 'true') return;
    node.dataset.removing = 'true';
    node.classList.add('is-leaving');
    window.setTimeout(() => node.remove(), 220);
  }

  function trimToastStack(target) {
    const nodes = [...target.querySelectorAll('.toast')];
    while (nodes.length > MESSAGE_LIMIT) removeToast(nodes.shift());
  }

  function wireToast(node, lifetime = MESSAGE_TTL) {
    if (!node || node.dataset.toastBound === 'true') return;
    node.dataset.toastBound = 'true';
    node.querySelector('[data-toast-close]')?.addEventListener('click', event => {
      event.preventDefault(); removeToast(node);
    });
    if (lifetime > 0) window.setTimeout(() => removeToast(node), lifetime);
  }

  function ensureStack() {
    let target = stack();
    if (target) return target;
    target = document.createElement('div');
    target.id = 'django-message-stack'; target.className = 'toast-stack';
    target.setAttribute('aria-live', 'polite'); target.setAttribute('aria-atomic', 'false');
    document.body.appendChild(target);
    return target;
  }

  function showDjangoMessage(text, level = 'info') {
    if (!text || typeof text !== 'string') return;
    const clean = text.replace(/\s+/g, ' ').trim().slice(0, 500);
    if (!clean || /^\s*[[{]/.test(clean)) return;
    const normalizedLevel = ['success', 'warning', 'error', 'info'].includes(level) ? level : 'info';
    const target = ensureStack();
    const recent = [...target.querySelectorAll('.toast')].slice(-1)[0];
    if (recent?.dataset.messageText === clean && recent?.dataset.toastLevel === normalizedLevel) return;

    const node = document.createElement('div');
    node.className = `toast ${normalizedLevel}`;
    node.dataset.toastLevel = normalizedLevel; node.dataset.messageText = clean;
    node.setAttribute('role', normalizedLevel === 'error' ? 'alert' : 'status');
    const message = document.createElement('span');
    message.className = 'toast-message'; message.textContent = clean;
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'toast-close'; button.dataset.toastClose = '1';
    button.setAttribute('aria-label', 'Close notification'); button.title = 'Close notification'; button.textContent = '×';
    node.append(message, button); target.appendChild(node);
    wireToast(node); trimToastStack(target);
  }

  window.AlgoBotMessage = showDjangoMessage;
  window.alert = message => showDjangoMessage(String(message ?? ''), 'info');

  function friendlyApiMessage(detail) {
    if (!detail) return 'The requested operation could not be completed.';
    const code = String(detail.code || '').toUpperCase();
    if (code === 'API_TIMEOUT') return 'The server took too long to respond. Please try again.';
    if (code === 'NETWORK_ERROR') return 'The data connection is temporarily unavailable. Please try again.';
    if (code === 'EDGE_CHALLENGE') return 'The production connection is temporarily unavailable. Please try again.';
    const message = String(detail.message || '').replace(/\s+/g, ' ').trim();
    if (!message || /^[[{]/.test(message) || message.length > 500) return 'The requested operation could not be completed.';
    return message;
  }

  function bindApiMessages() {
    window.addEventListener('algobot:api-error', event => {
      const detail = event.detail || {};
      const level = Number(detail.status) >= 500 || ['API_TIMEOUT', 'NETWORK_ERROR'].includes(detail.code) ? 'error' : 'warning';
      showDjangoMessage(friendlyApiMessage(detail), level);
    });
  }

  function bindNavigation() {
    const sidebar = $('#app-sidebar');
    if (!sidebar || sidebar.dataset.navigationBound === 'true') return;
    sidebar.dataset.navigationBound = 'true';
    const backdrop = $('[data-sidebar-backdrop]'); const mobile = $('[data-mobile-menu]');
    const toggle = $('[data-sidebar-toggle]'); const shell = $('.app-shell'); const storageKey = 'algobot.sidebar.collapsed';
    const setMobileOpen = open => {
      const next = !!open; sidebar.classList.toggle('is-open', next);
      if (backdrop) backdrop.hidden = !next;
      if (mobile) { mobile.setAttribute('aria-expanded', String(next)); mobile.setAttribute('aria-label', next ? 'Close navigation' : 'Open navigation'); }
      document.body.classList.remove('mobile-nav-open'); document.documentElement.classList.remove('mobile-nav-open');
    };
    setMobileOpen(false);
    document.addEventListener('click', event => {
      const target = event.target?.closest?.('[data-mobile-menu]');
      if (target) { event.preventDefault(); event.stopPropagation(); setMobileOpen(!sidebar.classList.contains('is-open')); return; }
      if (backdrop && (event.target === backdrop || event.target?.closest?.('[data-sidebar-backdrop]'))) { event.preventDefault(); setMobileOpen(false); return; }
      if (sidebar.classList.contains('is-open') && event.target?.closest?.('#app-sidebar nav a,#app-sidebar .sidebar-new-trade')) setMobileOpen(false);
    }, true);
    if (toggle) {
      const setCollapsed = collapsed => {
        if (window.innerWidth <= 900) return;
        sidebar.classList.toggle('is-collapsed', !!collapsed); shell?.classList.toggle('sidebar-collapsed', !!collapsed);
        document.body.classList.toggle('sidebar-collapsed', !!collapsed); toggle.setAttribute('aria-expanded', String(!collapsed));
        toggle.setAttribute('aria-label', collapsed ? 'Expand navigation' : 'Collapse navigation');
        const icon = toggle.querySelector('.material-symbols-rounded'); if (icon) icon.textContent = collapsed ? 'left_panel_open' : 'left_panel_close';
        try { localStorage.setItem(storageKey, collapsed ? '1' : '0'); } catch (_) { /* storage unavailable */ }
      };
      try { if (window.innerWidth > 900 && localStorage.getItem(storageKey) === '1') setCollapsed(true); } catch (_) { /* storage unavailable */ }
      toggle.addEventListener('click', event => { event.preventDefault(); event.stopPropagation(); setCollapsed(!sidebar.classList.contains('is-collapsed')); });
    }
    document.addEventListener('keydown', event => { if (event.key === 'Escape') setMobileOpen(false); });
    window.addEventListener('resize', () => { if (window.innerWidth > 900) setMobileOpen(false); });
  }

  function bindTheme() {
    const button = $('[data-theme-toggle]'); if (!button || button.dataset.themeBound === 'true') return;
    button.dataset.themeBound = 'true'; const storageKey = 'algobot-theme';
    const apply = theme => { document.documentElement.dataset.theme = theme; button.setAttribute('aria-pressed', String(theme === 'light')); };
    let stored = null; try { stored = localStorage.getItem(storageKey); } catch (_) { /* storage unavailable */ }
    if (stored === 'light' || stored === 'dark') apply(stored);
    button.addEventListener('click', () => {
      const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem(storageKey, next); } catch (_) { /* storage unavailable */ }
      apply(next);
    });
  }

  function boot() {
    bindNavigation(); bindTheme(); bindApiMessages();
    if (window.AlgoBotBrokerState) window.AlgoBotBrokerState.subscribe(setBrokerStateAttribute);
    const target = stack(); target?.querySelectorAll('.toast').forEach(node => wireToast(node, MESSAGE_TTL));
    if (target) trimToastStack(target);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true }); else boot();
})();
