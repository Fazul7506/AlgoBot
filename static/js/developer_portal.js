/* AlgoBot Developer portal: browser actions are native Django forms + messages. */
(() => {
  'use strict';
  if (window.__algoBotDeveloperPortal) return;
  window.__algoBotDeveloperPortal = true;

  const $ = (selector, root = document) => root.querySelector(selector);

  function bindConfirmations() {
    document.querySelectorAll('form[data-confirm]').forEach(form => {
      form.addEventListener('submit', event => {
        const message = form.dataset.confirm;
        if (message && !window.confirm(message)) event.preventDefault();
      });
    });
  }

  function bindCopyButtons() {
    document.querySelectorAll('[data-copy]').forEach(button => {
      button.addEventListener('click', async () => {
        const source = $(button.dataset.copy);
        const value = source?.textContent?.trim() || '';
        if (!value) return;
        try {
          await navigator.clipboard.writeText(value);
          button.textContent = 'Copied';
          window.setTimeout(() => { button.textContent = 'Copy'; }, 1400);
        } catch (_) {
          button.textContent = 'Copy failed';
          window.setTimeout(() => { button.textContent = 'Copy'; }, 1600);
        }
      });
    });
  }

  function bindSectionNavigation() {
    const links = [...document.querySelectorAll('.dev-dashboard .dev-tabs a')];
    if (!links.length) return;
    const updateActive = () => {
      const hash = window.location.hash || '#dev-overview';
      links.forEach(link => {
        const active = link.getAttribute('href') === hash;
        link.classList.toggle('is-active', active);
        if (active) link.setAttribute('aria-current', 'location');
        else link.removeAttribute('aria-current');
      });
    };
    links.forEach(link => link.addEventListener('click', () => {
      links.forEach(item => { item.classList.remove('is-active'); item.removeAttribute('aria-current'); });
      link.classList.add('is-active');
      link.setAttribute('aria-current', 'location');
    }));
    window.addEventListener('hashchange', updateActive);
    updateActive();
  }

  function boot() {
    if (!$('[data-developer-page]')) return;
    bindConfirmations();
    bindCopyButtons();
    bindSectionNavigation();
    $('[data-refresh-developer]')?.addEventListener('click', () => window.location.reload());
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
