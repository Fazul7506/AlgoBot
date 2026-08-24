/* AlgoBot icon runtime guard. Material Symbols are ligatures; never expose their raw names as fallback UI. */
(function () {
  'use strict';

  function verify() {
    var root = document.documentElement;
    var ready = false;
    if (document.fonts && document.fonts.check) {
      ready = document.fonts.check('24px "Material Symbols Rounded"');
    }
    root.toggleAttribute('data-icons-ready', ready);
    root.toggleAttribute('data-icons-fallback', !ready);
  }

  function boot() {
    verify();
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(verify);
    [250, 750, 1500, 3000].forEach(function (delay) { setTimeout(verify, delay); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
