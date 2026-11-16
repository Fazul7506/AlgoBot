/* Canonical AlgoBot monetary display.
 * AlgoBot uses USD exclusively: every monetary value is rendered with "$".
 * Currency formatting is presentation-only; this module never converts or
 * mutates broker/API values. Non-monetary values must not use this formatter.
 */
(() => {
  'use strict';
  if (window.__algoBotMoneyDisplay) return;
  window.__algoBotMoneyDisplay = true;
  const CURRENCY = 'USD';
  const SYMBOL = '$';
  const numberFor = value => {
    if (value == null || value === '' || typeof value === 'boolean') return 0;
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
  };
  const symbolFor = () => SYMBOL;
  const format = value => SYMBOL + numberFor(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
  const formatUSD = format;
  window.AlgoBotMoney = Object.freeze({
    currency: CURRENCY,
    symbol: SYMBOL,
    symbolFor,
    format,
    formatUSD,
    numberFor,
    isValid: value => value != null && value !== '' && typeof value !== 'boolean' && Number.isFinite(Number(value))
  });

  const monetaryText = /\$\s*-?\d[\d,]*(?:\.\d+)?/;
  const bareMoney = /^-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$/;
  function decorate(root = document) {
    if (!root || !document.body) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => {
      const parent = node.parentElement;
      if (!parent || /^(SCRIPT|STYLE|TEXTAREA|INPUT|CODE|PRE)$/i.test(parent.tagName)) return;
      const raw = (node.nodeValue || '').trim();
      if (parent.closest?.('.money-value') && bareMoney.test(raw)) {
        node.nodeValue = format(raw);
        parent.classList.add('algobot-money-value');
        return;
      }
      if (monetaryText.test(raw)) parent.classList.add('algobot-money-value');
    });
  }
  function boot() {
    decorate();
    const observer = new MutationObserver(records => records.forEach(record => {
      if (record.type === 'characterData') decorate(record.target.parentElement || document);
      else record.addedNodes.forEach(node => {
        if (node.nodeType === Node.ELEMENT_NODE) decorate(node);
        else if (node.nodeType === Node.TEXT_NODE && monetaryText.test(node.nodeValue || '')) {
          node.parentElement?.classList.add('algobot-money-value');
        }
      });
    }));
    observer.observe(document.body, {subtree: true, childList: true, characterData: true});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
