(() => {
  'use strict';
  // Keep the original sidebar behavior: the link whose route is the current
  // page (or the closest parent route) receives the visible active state.
  const normalize = value => {
    try { return new URL(value, window.location.origin).pathname.replace(/\/+$/, '') || '/'; }
    catch (_) { return ''; }
  };
  const markActiveNavigation = () => {
    const path = normalize(window.location.pathname);
    const links = [...document.querySelectorAll('.app-sidebar nav a[href], .sidebar-new-trade[href]')];
    let best = null;
    let bestLength = -1;
    links.forEach(link => {
      const target = normalize(link.getAttribute('href') || '');
      link.classList.remove('active', 'is-current-page');
      link.removeAttribute('aria-current');
      if (!target) return;
      const matched = target === '/'
        ? path === '/'
        : path === target || path.startsWith(`${target}/`);
      if (matched && target.length > bestLength) {
        best = link;
        bestLength = target.length;
      }
    });
    if (best) {
      best.classList.add('active', 'is-current-page');
      best.setAttribute('aria-current', 'page');
    }
  };
  const boot = () => {
    markActiveNavigation();
    // Some shell/page scripts render navigation after DOMContentLoaded.
    // Re-apply the same deterministic state without changing navigation.
    if (!window.__algoBotSidebarObserver) {
      const observer = new MutationObserver(() => markActiveNavigation());
      const sidebar = document.querySelector('.app-sidebar');
      if (sidebar) {
        observer.observe(sidebar, { childList: true, subtree: true, attributes: true, attributeFilter: ['href'] });
        window.__algoBotSidebarObserver = observer;
      }
    }
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
  window.addEventListener('pageshow', markActiveNavigation);
  window.addEventListener('popstate', markActiveNavigation);
})();