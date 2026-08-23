(() => {
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
