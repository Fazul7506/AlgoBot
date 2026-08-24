/* AlgoBot icon runtime guard
 * Material Symbols are ligatures. If the remote font cannot load, the ligature
 * becomes visible text. Replace failed ligatures with an inline SVG fallback so
 * an icon is ALWAYS rendered without exposing the icon name as UI text.
 */
(function () {
  'use strict';

  var ICON_SELECTOR = '.material-symbols-rounded';
  var FALLBACK_PATH = 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm1 5v4h4v2h-4v4h-2v-4H7v-2h4V7h2Z';

  function iconNodes() {
    return document.querySelectorAll(ICON_SELECTOR);
  }

  function replaceWithSvg(node) {
    if (!node || node.dataset.iconFallback === 'true') return;
    var name = (node.textContent || '').trim();
    if (!name) return;

    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    svg.setAttribute('class', 'algobot-icon-fallback');
    svg.dataset.iconName = name;

    var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', FALLBACK_PATH);
    path.setAttribute('fill', 'currentColor');
    svg.appendChild(path);

    node.textContent = '';
    node.appendChild(svg);
    node.dataset.iconFallback = 'true';
  }

  function restoreMaterialIcons() {
    iconNodes().forEach(function (node) {
      if (node.dataset.iconFallback === 'true') return;
      node.style.removeProperty('display');
    });
  }

  function verify() {
    if (!document.fonts || !document.fonts.check) return;
    var ready = document.fonts.check('24px "Material Symbols Rounded"');
    document.documentElement.toggleAttribute('data-icons-ready', ready);
    document.documentElement.toggleAttribute('data-icons-fallback', !ready);

    if (!ready) {
      iconNodes().forEach(replaceWithSvg);
    }
  }

  function boot() {
    verify();
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(function () {
        verify();
        restoreMaterialIcons();
      });
    }
    setTimeout(verify, 250);
    setTimeout(verify, 1000);
    setTimeout(verify, 2000);

    if (window.MutationObserver) {
      new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
          if (mutation.addedNodes && mutation.addedNodes.length) verify();
        });
      }).observe(document.documentElement, { childList: true, subtree: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
