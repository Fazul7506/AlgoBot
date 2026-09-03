(() => {
  'use strict';

  const StateManager = window.AlgoBotStateManager && window.AlgoBotStateManager.StateManager;
  const shell = {
    route: window.location.pathname,
    api: window.AlgoBotAPI && window.AlgoBotAPI.apiClient,
    state: StateManager ? new StateManager({
      isReady: false,
      route: window.location.pathname,
    }) : {
      set: () => {},
      get: () => undefined,
      subscribe: () => () => {},
    },
  };

  function updateActiveNavigation() {
    const currentPath = window.location.pathname.replace(/\/$/, '');
    const pathTargets = [
      document.querySelectorAll('#app-sidebar nav a'),
      document.querySelectorAll('#app-sidebar .sidebar-new-trade'),
    ];

    for (const group of pathTargets) {
      group.forEach((link) => {
        const href = (link.getAttribute('href') || '').replace(/\/$/, '');
        const active = href && (currentPath === href || (currentPath.startsWith(href) && href !== '/'));
        link.classList.toggle('active', active);
        if (active) {
          link.setAttribute('aria-current', 'page');
        } else {
          link.removeAttribute('aria-current');
        }
      });
    }
  }

  function bindToastClose() {
    document.querySelectorAll('[data-toast-close]').forEach((button) => {
      button.addEventListener('click', () => {
        const toast = button.closest('[data-django-message]');
        if (!toast) return;
        toast.remove();
      });
    });
  }

  function bindSidebarToggle() {
    const toggle = document.querySelector('[data-sidebar-toggle]');
    const sidebar = document.getElementById('app-sidebar');
    const appShell = document.querySelector('.app-shell');
    const backdrop = document.querySelector('[data-sidebar-backdrop]');
    const mobileButton = document.querySelector('[data-mobile-menu]');

    if (!toggle || !sidebar || !appShell) return;

    toggle.addEventListener('click', () => {
      const collapsed = sidebar.classList.toggle('is-collapsed');
      appShell.classList.toggle('sidebar-collapsed', collapsed);
      toggle.setAttribute('aria-expanded', String(!collapsed));
    });

    if (backdrop) {
      backdrop.addEventListener('click', () => {
        sidebar.classList.remove('is-open');
        backdrop.hidden = true;
        if (mobileButton) {
          mobileButton.setAttribute('aria-expanded', 'false');
        }
      });
    }

    if (mobileButton) {
      mobileButton.addEventListener('click', () => {
        const expanded = mobileButton.getAttribute('aria-expanded') === 'true';
        sidebar.classList.toggle('is-open', !expanded);
        backdrop.hidden = !(!expanded);
        mobileButton.setAttribute('aria-expanded', String(!expanded));
      });
    }
  }

  function bindThemeToggle() {
    const button = document.querySelector('[data-theme-toggle]');
    if (!button) return;

    const root = document.documentElement;
    button.addEventListener('click', () => {
      const nextTheme = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', nextTheme);
      button.setAttribute('aria-pressed', String(nextTheme === 'light'));
    });
  }

  function hydrateShell() {
    const main = document.getElementById('main-content');
    if (main && !main.hasAttribute('tabindex')) {
      main.setAttribute('tabindex', '-1');
    }

    updateActiveNavigation();
    bindToastClose();
    bindSidebarToggle();
    bindThemeToggle();

    shell.state.set('isReady', true);
    shell.state.set('route', shell.route);
    document.body.dataset.frontendShell = 'ready';
  }

  document.addEventListener('DOMContentLoaded', hydrateShell);
  if (document.readyState !== 'loading') {
    hydrateShell();
  }

  window.AlgoBotFrontendShell = Object.freeze({
    api: shell.api,
    state: shell.state,
    updateActiveNavigation,
    hydrateShell,
  });
})();
