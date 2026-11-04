(() => {
  'use strict';
  if (window.__algobotWorkspaceTabs) return;
  window.__algobotWorkspaceTabs = true;

  const roots = [...document.querySelectorAll('[data-workspace-tabs]')];
  roots.forEach((nav) => {
    const content = nav.parentElement?.querySelector('[data-workspace-tab-content]') ||
      nav.nextElementSibling?.matches('[data-workspace-tab-content]') && nav.nextElementSibling;
    if (!content) return;
    const tabs = [...nav.querySelectorAll('a[href^="#"]')].map((link) => ({
      link,
      id: decodeURIComponent(link.getAttribute('href').slice(1)),
      panel: document.getElementById(decodeURIComponent(link.getAttribute('href').slice(1)))
    })).filter((item) => item.panel && content.contains(item.panel));
    if (!tabs.length) return;
    tabs.forEach(({link, id, panel}) => {
      if (!link.id) link.id = 'workspace-tab-' + id;
      link.setAttribute('aria-controls', panel.id);
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', link.id);
      if (!panel.hasAttribute('tabindex')) panel.tabIndex = 0;
    });

    const activate = (selected, updateUrl = true, focus = false) => {
      if (!selected?.panel) return;
      tabs.forEach(({link, panel}) => {
        const active = panel === selected.panel;
        link.classList.toggle('is-active', active);
        link.setAttribute('aria-selected', String(active));
        link.tabIndex = active ? 0 : -1;
      });

      const isolate = (parent) => {
        [...parent.children].forEach((child) => {
          const keep = child === selected.panel || child.contains(selected.panel);
          child.hidden = !keep;
          child.classList.toggle('workspace-tab-hidden', !keep);
          if (keep && child !== selected.panel) isolate(child);
        });
      };
      isolate(content);
      if (updateUrl && window.history?.replaceState) {
        window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${selected.id}`);
      }
      if (focus) selected.link.focus();
      content.dispatchEvent(new CustomEvent('algobot:workspace-tab-changed', {detail: {id: selected.id}}));
    };

    nav.addEventListener('click', (event) => {
      const link = event.target.closest('a[href^="#"]');
      if (!link || !nav.contains(link)) return;
      const selected = tabs.find((item) => item.link === link);
      if (!selected) return;
      event.preventDefault();
      activate(selected);
    });

    nav.addEventListener('keydown', (event) => {
      const current = tabs.findIndex((item) => item.link === document.activeElement);
      if (current < 0) return;
      let next = current;
      if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (current + 1) % tabs.length;
      else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (current - 1 + tabs.length) % tabs.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = tabs.length - 1;
      else return;
      event.preventDefault();
      activate(tabs[next], true, true);
    });

    const initial = tabs.find((item) => item.id === decodeURIComponent(window.location.hash.slice(1))) || tabs[0];
    activate(initial, false);
    window.addEventListener('popstate', () => {
      const target = tabs.find((item) => item.id === decodeURIComponent(window.location.hash.slice(1)));
      if (target) activate(target, false);
    });

    document.addEventListener('click', (event) => {
      const link = event.target.closest('a[href^="#"]');
      if (!link || nav.contains(link)) return;
      const id = decodeURIComponent(link.getAttribute('href').slice(1));
      const selected = tabs.find((item) => item.id === id);
      if (!selected || !content.contains(link)) return;
      event.preventDefault();
      activate(selected);
      selected.link.focus({preventScroll: true});
    });
  });
})();
