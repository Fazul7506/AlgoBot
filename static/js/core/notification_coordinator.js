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
  let lastToast = '';
  let lastToastAt = 0;

  const normalize = value => String(value || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const isGeneric = value => {
    const text = normalize(value);
    return GENERIC.has(text) || text.startsWith('data connection issue failed to fetch');
  };

  function removeDuplicateGenericToasts(root = document) {
    const nodes = [...root.querySelectorAll?.('.toast-stack .toast, #django-message-stack .toast') || []];
    const railVisible = !!document.querySelector('.algobot-recovery-rail:not([hidden])');
    nodes.forEach(node => {
      const text = normalize(node.textContent);
      if (railVisible && isGeneric(text)) node.remove();
    });
  }

  function bindStack(stack) {
    if (!stack || stack.dataset.notificationCoordinator === 'true') return;
    stack.dataset.notificationCoordinator = 'true';
    stack.addEventListener('DOMNodeInserted', () => removeDuplicateGenericToasts(stack));
  }

  function startObserver() {
    if (observer || !document.body) return;
    observer = new MutationObserver(mutations => {
      for (const mutation of mutations) {
        mutation.addedNodes?.forEach(node => {
          if (node.nodeType !== 1) return;
          if (node.matches?.('.toast-stack, #django-message-stack')) bindStack(node);
          if (node.matches?.('.toast, .algobot-recovery-rail') || node.querySelector?.('.toast, .algobot-recovery-rail')) {
            removeDuplicateGenericToasts(document);
          }
        });
      }
    });
    observer.observe(document.body, {childList:true, subtree:true});
    bindStack(document.querySelector('#django-message-stack'));
    removeDuplicateGenericToasts(document);
  }

  window.addEventListener('algobot:recoverable-error', event => {
    const detail = event.detail || {};
    const signature = `${normalize(detail.code)}|${normalize(detail.url)}|${Number(detail.status || 0)}|${normalize(detail.message)}`;
    const now = Date.now();
    if (signature === lastToast && now - lastToastAt < 1500) return;
    lastToast = signature;
    lastToastAt = now;
    window.setTimeout(() => removeDuplicateGenericToasts(document), 0);
  });

  const boot = () => startObserver();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true});
  else boot();
})();
