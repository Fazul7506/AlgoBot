/* Canonical AlgoBot monetary display.
 * AlgoBot is USD-only. Every monetary value and placeholder uses "$".
 * Currency metadata from providers is retained for audit but never changes
 * AlgoBot's display currency. This is formatting only, not conversion.
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
  // Normalize bare numeric text in monetary UI containers after both initial
  // render and asynchronous DOM updates. This is presentation-only; provider
  // payloads and stored account currency metadata are never changed.
  const bareMoney = /^\s*-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?\s*$/;
  const decorate = node => {
    if (!node || node.nodeType !== 3) return;
    const parent = node.parentElement;
    if (!parent || !parent.closest?.('.money-value')) return;
    const raw = node.nodeValue || '';
    if (bareMoney.test(raw)) node.nodeValue = format(raw);
  };
  const normalize = root => {
    if (!root) return;
    const targets = root.matches?.('.money-value') ? [root] : Array.from(root.querySelectorAll?.('.money-value') || []);
    targets.forEach(element => {
      element.childNodes.forEach(node => {
        if (node.nodeType === 1) normalize(node);
        else if (node.nodeType === Node.TEXT_NODE) decorate(node);
      });
    });
    if (root.nodeType === 3) decorate(root);
  };
  const startNormalization = () => {
    normalize(document);
    if (typeof MutationObserver !== 'undefined' && document.documentElement) {
      const observer = new MutationObserver(records => records.forEach(record => {
        if (record.type === 'characterData') decorate(record.target);
        record.addedNodes?.forEach(node => normalize(node));
      }));
      observer.observe(document.documentElement, {subtree: true, childList: true, characterData: true});
    }
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', startNormalization, {once: true});
  else startNormalization();

  window.AlgoBotMoney = Object.freeze({
    currency: CURRENCY,
    symbol: SYMBOL,
    symbolFor,
    format,
    formatUSD: format,
    numberFor,
    isValid: value => value != null && value !== '' && typeof value !== 'boolean' && Number.isFinite(Number(value))
  });
})();
