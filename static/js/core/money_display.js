/* AlgoBot money presentation layer.
 * Data/API currency codes remain authoritative. This changes presentation only:
 * USD monetary values render with the dollar sign while non-USD currencies keep
 * their broker-provided code/symbol.
 */
(() => {
  'use strict';
  if (window.__algoBotMoneyDisplay) return;
  window.__algoBotMoneyDisplay = true;

  const symbols = Object.freeze({USD:'$', KES:'KSh ', EUR:'€', GBP:'£', JPY:'¥', CNY:'¥', AUD:'A$', CAD:'C$', CHF:'CHF '});
  const symbolFor = currency => symbols[String(currency || '').trim().toUpperCase()] || null;
  const format = (value, currency='USD') => {
    if (value == null || value === '' || Number.isNaN(Number(value))) return '—';
    const symbol = symbolFor(currency) || String(currency || '').trim() + (currency ? ' ' : '');
    return symbol + Number(value).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:8});
  };

  window.AlgoBotMoney = Object.freeze({symbols, symbolFor, format});

  // Cover the common server-rendered and client-rendered money shapes while
  // deliberately leaving plain currency labels such as "USD" untouched.
  const numeric = '(-?(?:\\d{1,3}(?:,\\d{3})+|\\d+)(?:\\.\\d+)?)';
  const moneyPattern = new RegExp('(^|[\\s(])USD(?:[\\s\\u00a0:]+)'+numeric+'(?=$|[\\s\\u00a0,)])','gi');
  const suffixPattern = new RegExp(numeric+'[\\s\\u00a0]+USD(?=$|[\\s\\u00a0,)])','gi');

  function transformTextNode(node) {
    const parent = node.parentElement;
    if (!parent || /^(SCRIPT|STYLE|TEXTAREA|INPUT|CODE|PRE)$/i.test(parent.tagName)) return;
    const text = node.nodeValue || '';
    if (!/USD/i.test(text) || !/\d/.test(text)) return;
    const next = text
      .replace(moneyPattern, (_, prefix, amount) => `${prefix}${amount}`)
      .replace(suffixPattern, (_, amount) => `${amount}`);
    if (next !== text) node.nodeValue = next;
  }

  function scan(root=document) {
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
    const nodes=[];
    while(walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(transformTextNode);
  }

  function boot() {
    scan();
    const observer=new MutationObserver(records => {
      for (const record of records) {
        if (record.type === 'characterData') transformTextNode(record.target);
        else record.addedNodes.forEach(node => {
          if (node.nodeType === Node.TEXT_NODE) transformTextNode(node);
          else if (node.nodeType === Node.ELEMENT_NODE) scan(node);
        });
      }
    });
    observer.observe(document.body,{subtree:true,childList:true,characterData:true});
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();