(() => {
  const notify = (message, type = 'info') => {
    let stack = document.querySelector('.toast-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'toast-stack';
      stack.setAttribute('aria-live', 'polite');
      document.body.appendChild(stack);
    }
    const node = document.createElement('div');
    node.className = `toast ${type}`;
    node.setAttribute('role', 'status');
    node.textContent = String(message || '');
    stack.appendChild(node);
    window.setTimeout(() => node.remove(), 4500);
  };

  // Legacy UI code may still call alert(); keep all user feedback in the
  // application's notification system instead of browser modal dialogs.
  window.alert = message => notify(message, 'info');

  const isApiUrl = value => {
    try { return new URL(value, window.location.origin).pathname.startsWith('/api/'); }
    catch { return false; }
  };

  const clean = root => {
    (root || document).querySelectorAll('a[href]').forEach(anchor => {
      if (isApiUrl(anchor.getAttribute('href'))) anchor.remove();
    });
    (root || document).querySelectorAll('[data-resource-list]').forEach(node => {
      node.textContent = 'Live platform services are available through the workspace. Internal API routes are not user-facing.';
    });
  };

  clean(document);
  const observer = new MutationObserver(mutations => mutations.forEach(m => m.addedNodes.forEach(node => {
    if (node.nodeType === Node.ELEMENT_NODE) clean(node);
  })));
  observer.observe(document.body, { childList: true, subtree: true });
})();
