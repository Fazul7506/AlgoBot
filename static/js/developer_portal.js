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

  function boot() {
    if (!$('[data-developer-page]')) return;
    bindConfirmations();
    bindCopyButtons();
    $('[data-refresh-developer]')?.addEventListener('click', () => window.location.reload());
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
