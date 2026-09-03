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
    return window.AlgoBotBaseShell?.syncActiveNavigation?.({anchor: true});
  }

  function bindToastClose() {
    document.querySelectorAll('[data-toast-close]').forEach((button) => {
      if (button.dataset.shellBound === 'true') return;
      button.dataset.shellBound = 'true';
      button.addEventListener('click', () => {
        const toast = button.closest('[data-django-message]');
        if (!toast) return;
        toast.remove();
      });
    });
  }

  function bindSidebarToggle() {
    // Navigation, collapse state, mobile drawer, and active highlighting are
    // owned by base_shell.js. This module only exposes the legacy shell API.
  }

  function bindThemeToggle() {
    // Theme state is owned by base_shell.js to avoid duplicate event handlers.
  }

  function hydrateShell() {
    const main = document.getElementById('main-content');
    if (main && !main.hasAttribute('tabindex')) main.setAttribute('tabindex', '-1');
    updateActiveNavigation();
    bindToastClose();
    bindSidebarToggle();
    bindThemeToggle();
    shell.state.set('isReady', true);
    shell.state.set('route', shell.route);
    document.body.dataset.frontendShell = 'ready';
  }

  document.addEventListener('DOMContentLoaded', hydrateShell);
  if (document.readyState !== 'loading') hydrateShell();

  window.AlgoBotFrontendShell = Object.freeze({
    api: shell.api,
    state: shell.state,
    updateActiveNavigation,
    hydrateShell,
  });
})();
