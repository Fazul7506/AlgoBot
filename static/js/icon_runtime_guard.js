/* AlgoBot icon runtime guard
 * Material Symbols are ligatures. If the font is unavailable, the raw ligature
 * becomes visible text. Keep the icon node visually reserved and retry font
 * readiness rather than replacing the semantic label with fallback text.
 */
(function () {
  'use strict';

  function iconNodes() {
    return document.querySelectorAll('.material-symbols-rounded');
  }

  function verify() {
    if (!document.fonts || !document.fonts.check) return;
    var ready = document.fonts.check('24px "Material Symbols Rounded"');
    document.documentElement.toggleAttribute('data-icons-ready', ready);
    document.documentElement.toggleAttribute('data-icons-fallback', !ready);
  }

  function boot() {
    verify();
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(verify);
    }
    setTimeout(verify, 500);
    setTimeout(verify, 1500);
    void iconNodes();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
