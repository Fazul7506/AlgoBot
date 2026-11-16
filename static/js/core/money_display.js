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
