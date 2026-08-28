/* Global workspace recovery UX: visible diagnostics without fabricating data. */
(() => {
  'use strict';
  if (window.__algoBotWorkspaceRecovery) return;
  window.__algoBotWorkspaceRecovery = true;

  const esc = value => String(value ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[c]));
  let rail;
  let hideTimer;
  let lastSignature = '';

  function ensureRail() {
    if (rail) return rail;
    rail = document.createElement('aside');
    rail.className = 'algobot-recovery-rail';
    rail.setAttribute('aria-live', 'polite');
    rail.hidden = true;
    rail.innerHTML = '<div class="algobot-recovery-icon" aria-hidden="true">!</div><div class="algobot-recovery-copy"><strong data-recovery-title>Data connection issue</strong><span data-recovery-message></span></div><button type="button" data-recovery-retry>Retry</button><button type="button" class="algobot-recovery-close" data-recovery-close aria-label="Dismiss">×</button>';
    document.body.appendChild(rail);
    rail.querySelector('[data-recovery-close]').addEventListener('click', () => { rail.hidden = true; });
    return rail;
  }

  function show(detail) {
    const node = ensureRail();
    const title = node.querySelector('[data-recovery-title]');
    const message = node.querySelector('[data-recovery-message]');
    const retry = node.querySelector('[data-recovery-retry]');
    const signature = `${detail.code}|${detail.url}|${detail.status}`;
    if (signature === lastSignature && !node.hidden) return;
    lastSignature = signature;
    node.dataset.state = detail.edgeChallenge ? 'edge' : 'error';
    title.textContent = detail.edgeChallenge ? 'Production edge protection interrupted the request' : 'Data connection issue';
    message.textContent = detail.edgeChallenge
      ? 'No market or trading data was fabricated. Retry when the edge challenge clears.'
      : (detail.message || 'The backend did not return usable data.');
    retry.hidden = !detail.retryable;
    retry.onclick = detail.retryable && typeof detail.retry === 'function' ? detail.retry : null;
    node.hidden = false;
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => { if (node) node.hidden = true; }, detail.edgeChallenge ? 12000 : 9000);
  }

  window.addEventListener('algobot:api-error', event => {
    const detail = event.detail || {};
    show(detail);
  });

  window.addEventListener('keydown', event => {
    if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'r' || event.shiftKey || event.altKey) return;
    const active = document.activeElement;
    if (active && /^(input|textarea|select)$/.test(active.tagName.toLowerCase())) return;
    const button = rail?.querySelector('[data-recovery-retry]');
    if (button && !button.hidden) { event.preventDefault(); button.click(); }
  });

  const style = document.createElement('style');
  style.textContent = `.algobot-recovery-rail{position:fixed;z-index:9999;right:18px;bottom:18px;max-width:min(520px,calc(100vw - 36px));display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;gap:10px;align-items:center;padding:12px 14px;border:1px solid rgba(245,158,11,.35);border-radius:12px;background:rgba(20,24,31,.97);box-shadow:0 14px 40px rgba(0,0,0,.35);color:#e5e7eb}.algobot-recovery-rail[data-state="edge"]{border-color:rgba(239,68,68,.42)}.algobot-recovery-icon{width:25px;height:25px;border-radius:50%;display:grid;place-items:center;background:#f59e0b;color:#111827;font-weight:800}.algobot-recovery-rail[data-state="edge"] .algobot-recovery-icon{background:#ef4444;color:#fff}.algobot-recovery-copy{min-width:0}.algobot-recovery-copy strong,.algobot-recovery-copy span{display:block}.algobot-recovery-copy strong{font-size:12px}.algobot-recovery-copy span{margin-top:2px;color:#94a3b8;font-size:11px;line-height:1.4}.algobot-recovery-rail button{border:0;border-radius:7px;padding:7px 10px;background:#e5e7eb;color:#111827;font-weight:700;cursor:pointer}.algobot-recovery-rail .algobot-recovery-close{background:transparent;color:#94a3b8;font-size:18px;padding:2px 5px}@media(max-width:600px){.algobot-recovery-rail{right:10px;bottom:10px;max-width:calc(100vw - 20px);grid-template-columns:auto minmax(0,1fr) auto}.algobot-recovery-close{grid-column:3;grid-row:1}.algobot-recovery-rail [data-recovery-retry]{grid-column:2;justify-self:start}}`;
  document.head.appendChild(style);
})();
