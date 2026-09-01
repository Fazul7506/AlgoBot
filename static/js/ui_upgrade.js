(() => {
  'use strict';
  // base_shell.js owns navigation behavior; this module only reinforces the
  // visual/current-page contract after other page scripts mutate the DOM.
  const normalize = value => { try { return new URL(value, window.location.origin).pathname.replace(/\/+$/, '') || '/'; } catch (_) { return ''; } };
  const markActiveNavigation = () => {
    const path = normalize(window.location.pathname);
    const links = [...document.querySelectorAll('#app-sidebar nav a[href], #app-sidebar .sidebar-new-trade[href]')];
    let best = null, bestLength = -1;
    links.forEach(link => {
      const target = normalize(link.getAttribute('href') || '');
      const matched = target === '/' ? path === '/' : path === target || path.startsWith(`${target}/`);
      link.classList.remove('active', 'is-current-page');
      link.removeAttribute('aria-current');
      if (matched && target.length > bestLength) { best = link; bestLength = target.length; }
    });
    if (best) {
      best.classList.add('active', 'is-current-page');
      best.setAttribute('aria-current', 'page');
      try { best.scrollIntoView({block:'nearest', inline:'nearest'}); } catch (_) {}
    }
  };
  const bindCommandShortcut = () => {
    if (document.body.dataset.commandShortcutBound === 'true') return;
    document.body.dataset.commandShortcutBound = 'true';
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') document.querySelector('[data-sidebar-backdrop]')?.click();
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        document.querySelector('input[type="search"], [data-command-search]')?.focus();
      }
    });
  };
  const boot = () => { markActiveNavigation(); bindCommandShortcut(); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true }); else boot();
  window.addEventListener('popstate', markActiveNavigation);
})();