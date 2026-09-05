/* AlgoBot canonical notification boundary.
 * Network/recovery failures are rendered once by workspace_recovery.js.
 * Legacy toast producers remain compatible, but duplicate generic network
 * overlays are removed so one backend failure never covers the workspace.
 */
(() => {
  'use strict';
  if (window.__algoBotNotificationCoordinator) return;
  window.__algoBotNotificationCoordinator = true;

  const GENERIC = new Set([
    'failed to fetch',
    'the data connection is temporarily unavailable. please try again.',
    'data connection issue',
    'data connection issue failed to fetch'
  ]);
  let observer = null;
  let lastSignature = '';
  let lastAt = 0;

  const normalize = value => String(value || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const isGeneric = value => {
    const text = normalize(value);
    return GENERIC.has(text) || text.startsWith('data connection issue failed to fetch');
  };

  function removeDuplicateGenericToasts(root = document) {
    const nodes = [...(root.querySelectorAll?.('.toast-stack .toast, #django-message-stack .toast') || [])];
    const seen = new Set();
    nodes.forEach(node => {
      const text = normalize(node.textContent);
      if (isGeneric(text)) {
        node.remove();
        return;
      }
      if (text && seen.has(text)) node.remove();
      else if (text) seen.add(text);
    });
  }

  function startObserver() {
    if (observer || !document.body) return;
    observer = new MutationObserver(mutations => {
      let relevant = false;
      for (const mutation of mutations) {
        mutation.addedNodes?.forEach(node => {
          if (node.nodeType === 1 && (node.matches?.('.toast, .toast-stack, #django-message-stack, .algobot-recovery-rail') || node.querySelector?.('.toast, .algobot-recovery-rail'))) relevant = true;
        });
      }
      if (relevant) removeDuplicateGenericToasts(document);
    });
    observer.observe(document.body, {childList:true, subtree:true});
    removeDuplicateGenericToasts(document);
  }

  window.addEventListener('algobot:recoverable-error', event => {
    const detail = event.detail || {};
    const signature = `${normalize(detail.code)}|${normalize(detail.url)}|${Number(detail.status || 0)}|${normalize(detail.message)}`;
    const now = Date.now();
    if (signature === lastSignature && now - lastAt < 1500) return;
    lastSignature = signature;
    lastAt = now;
    window.setTimeout(() => removeDuplicateGenericToasts(document), 0);
  });

  const boot = () => startObserver();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true});
  else boot();
})();
