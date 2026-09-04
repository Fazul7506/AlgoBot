(() => {
  'use strict';

  class StateManager {
    constructor(initial = {}) {
      this.state = typeof structuredClone === 'function' ? structuredClone(initial) : JSON.parse(JSON.stringify(initial));
      this.listeners = new Set();
    }
    set(path, value) {
      const keys = path.split('.');
      const next = this.deepClone(this.state);
      let cursor = next;
      for (let index = 0; index < keys.length - 1; index += 1) {
        const key = keys[index];
        if (cursor[key] == null || typeof cursor[key] !== 'object') cursor[key] = {};
        cursor = cursor[key];
      }
      cursor[keys[keys.length - 1]] = value;
      this.state = next;
      this.emit();
      return this.state;
    }
    get(path, fallback = undefined) {
      const keys = path.split('.');
      let value = this.state;
      for (const key of keys) {
        if (value == null || !Object.prototype.hasOwnProperty.call(value, key)) return fallback;
        value = value[key];
      }
      return value;
    }
    subscribe(listener) {
      if (typeof listener !== 'function') return () => {};
      this.listeners.add(listener);
      return () => this.listeners.delete(listener);
    }
    emit() {
      for (const listener of this.listeners) {
        try { listener(this.state); } catch (error) { setTimeout(() => { throw error; }, 0); }
      }
    }
    deepClone(value) {
      if (value === null || typeof value !== 'object') return value;
      if (typeof structuredClone === 'function') {
        try { return structuredClone(value); } catch (_) { /* fall through */ }
      }
      return JSON.parse(JSON.stringify(value));
    }
  }

  // Keep the legacy public namespace while making this module the single
  // canonical owner of shell state and state-management behavior.
  window.AlgoBotStateManager = Object.freeze({ StateManager });

  const shell = {
    route: window.location.pathname,
    api: window.AlgoBotAPI && window.AlgoBotAPI.apiClient,
    state: new StateManager({ isReady: false, route: window.location.pathname }),
  };

  function updateActiveNavigation() {
    return window.AlgoBotBaseShell?.syncActiveNavigation?.({ anchor: true });
  }

  function bindToastClose() {
    document.querySelectorAll('[data-toast-close]').forEach((button) => {
      if (button.dataset.shellBound === 'true') return;
      button.dataset.shellBound = 'true';
      button.addEventListener('click', () => {
        const toast = button.closest('[data-django-message]');
        if (toast) toast.remove();
      });
    });
  }

  function hydrateShell() {
    const main = document.getElementById('main-content');
    if (main && !main.hasAttribute('tabindex')) main.setAttribute('tabindex', '-1');
    updateActiveNavigation();
    bindToastClose();
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
