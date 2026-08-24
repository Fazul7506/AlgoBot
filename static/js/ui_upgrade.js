(() => {
  'use strict';

  // Navigation ownership lives in base_shell.js. This module is intentionally
  // limited to page-level enhancements so two scripts cannot bind the same
  // sidebar/menu controls and fight over state.
  const markActiveNavigation = () => {
    const path = window.location.pathname;
    document.querySelectorAll('.app-sidebar nav a, .sidebar-new-trade').forEach(link => {
      const href = link.getAttribute('href');
      if (!href || href === '/') return;
      link.classList.toggle('active', path === href || (href !== '/' && path.startsWith(href)));
    });
  };

  const bindCommandShortcut = () => {
    if (document.body.dataset.commandShortcutBound === 'true') return;
    document.body.dataset.commandShortcutBound = 'true';
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        document.querySelector('[data-sidebar-backdrop]')?.click();
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        document.querySelector('input[type="search"], [data-command-search]')?.focus();
      }
    });
  };

  const boot = () => {
    markActiveNavigation();
    bindCommandShortcut();
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
