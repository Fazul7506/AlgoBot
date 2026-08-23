(() => {
  const body = document.body;
  const menu = document.querySelector('[data-mobile-menu]');
  const backdrop = document.querySelector('[data-sidebar-backdrop]');
  const sidebar = document.querySelector('.app-sidebar');
  const collapse = document.querySelector('[data-sidebar-toggle]');

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
    if (!sidebar) return;
    sidebar.classList.toggle('is-collapsed', collapsed);
    collapse?.setAttribute('aria-expanded', String(!collapsed));
    collapse?.setAttribute('aria-label', collapsed ? 'Expand navigation' : 'Collapse navigation');
    const icon = collapse?.querySelector('.material-symbols-rounded');
    if (icon) icon.textContent = collapsed ? 'menu' : 'menu_open';
    localStorage.setItem(storageKey, collapsed ? '1' : '0');
  };
  if (window.innerWidth > 800 && localStorage.getItem(storageKey) === '1') setCollapsed(true);
  collapse?.addEventListener('click', () => {
    if (window.innerWidth <= 800) return;
    setCollapsed(!sidebar?.classList.contains('is-collapsed'));
  });

  document.querySelectorAll('.app-sidebar nav a').forEach(link => {
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

  const accountButton = document.querySelector('[data-account-menu]');
  const accountDropdown = document.querySelector('[data-account-dropdown]');
  accountButton?.addEventListener('click', () => {
    const open = accountDropdown?.hidden === false;
    if (accountDropdown) accountDropdown.hidden = open;
    accountButton.setAttribute('aria-expanded', String(!open));
  });
  document.addEventListener('click', event => {
    if (accountDropdown && accountButton && !accountButton.contains(event.target) && !accountDropdown.contains(event.target)) {
      accountDropdown.hidden = true;
      accountButton.setAttribute('aria-expanded', 'false');
    }
  });
  window.addEventListener('resize', () => {
    if (window.innerWidth > 800) {
      closeMobile();
      if (localStorage.getItem(storageKey) === '1') setCollapsed(true);
    }
  });
})();
