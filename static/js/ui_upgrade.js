(() => {
  const body = document.body;
  const menu = document.querySelector('[data-mobile-menu]');
  const backdrop = document.querySelector('[data-sidebar-backdrop]');
  const sidebar = document.querySelector('.app-sidebar');
  const collapse = document.querySelector('[data-sidebar-toggle]');
  if (!sidebar) return;

  const closeMobile = () => {
    body.classList.remove('mobile-nav-open');
    menu?.setAttribute('aria-expanded', 'false');
    if (backdrop) backdrop.hidden = true;
  };
  const openMobile = () => {
    body.classList.add('mobile-nav-open');
    menu?.setAttribute('aria-expanded', 'true');
    if (backdrop) backdrop.hidden = false;
  };
  menu?.addEventListener('click', () => body.classList.contains('mobile-nav-open') ? closeMobile() : openMobile());
  backdrop?.addEventListener('click', closeMobile);

  const storageKey = 'algobot.sidebar.collapsed';
  const setCollapsed = collapsed => {
    if (window.innerWidth <= 800) return;
    sidebar.classList.toggle('is-collapsed', collapsed);
    collapse?.setAttribute('aria-expanded', String(!collapsed));
    collapse?.setAttribute('aria-label', collapsed ? 'Expand navigation' : 'Collapse navigation');
    const icon = collapse?.querySelector('.material-symbols-rounded');
    if (icon) icon.textContent = collapsed ? 'left_panel_open' : 'left_panel_close';
    try { localStorage.setItem(storageKey, collapsed ? '1' : '0'); } catch (_) {}
  };
  try { if (window.innerWidth > 800 && localStorage.getItem(storageKey) === '1') setCollapsed(true); } catch (_) {}
  collapse?.addEventListener('click', () => setCollapsed(!sidebar.classList.contains('is-collapsed')));

  document.querySelectorAll('.app-sidebar nav a, .sidebar-new-trade').forEach(link => {
    const href = link.getAttribute('href');
    if (href && href !== '/' && window.location.pathname.startsWith(href)) link.classList.add('active');
    link.addEventListener('click', () => { if (window.innerWidth <= 800) closeMobile(); });
  });

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') closeMobile();
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      const search = document.querySelector('input[type="search"], [data-command-search]');
      search?.focus();
    }
  });

  window.addEventListener('resize', () => {
    if (window.innerWidth > 800) closeMobile();
  });
})();
