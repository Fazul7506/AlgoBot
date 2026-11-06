/* Canonical monetary display. API currency codes remain authoritative.
 * Missing/invalid monetary values render as zero; no value is fabricated in
 * storage or API responses. USD is the platform billing/display default.
 */
(() => {
  'use strict';
  if (window.__algoBotMoneyDisplay) return;
  window.__algoBotMoneyDisplay = true;
  const symbols = Object.freeze({USD:'$', KES:'KSh ', EUR:'€', GBP:'£', JPY:'¥', CNY:'¥', AUD:'A$', CAD:'C$', CHF:'CHF ', UGX:'USh ', TZS:'TSh ', RWF:'FRw '});
  const codeFor = currency => String(currency || 'USD').trim().toUpperCase() || 'USD';
  const symbolFor = currency => symbols[codeFor(currency)] || `${codeFor(currency)} `;
  const numberFor = value => {
    if (value == null || value === '' || typeof value === 'boolean') return 0;
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
  };
  const format = (value, currency='USD') => `${symbolFor(currency)}${numberFor(value).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}`;
  const formatUSD = value => format(value, 'USD');
  window.AlgoBotMoney = Object.freeze({symbols, symbolFor, format, formatUSD, numberFor, isValid:value=>value!=null&&value!==''&&Number.isFinite(Number(value))});

  const monetaryText = /(?:\$|KSh\s|USD\s|EUR\s|GBP\s|€|£|¥|A\$|C\$|CHF\s|USh\s|TSh\s|FRw\s)\s*-?\d[\d,]*(?:\.\d+)?/i;
  function decorate(root=document) {
    if (!root || !document.body) return;
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
    const nodes=[];
    while(walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node=>{
      const parent=node.parentElement;
      if(!parent || /^(SCRIPT|STYLE|TEXTAREA|INPUT|CODE|PRE)$/i.test(parent.tagName)) return;
      if(monetaryText.test(node.nodeValue||'')) parent.classList.add('algobot-money-value');
    });
  }
  function boot(){
    decorate();
    const observer=new MutationObserver(records=>records.forEach(record=>{
      if(record.type==='characterData') decorate(record.target.parentElement||document);
      else record.addedNodes.forEach(node=>{if(node.nodeType===Node.ELEMENT_NODE)decorate(node);else if(node.nodeType===Node.TEXT_NODE&&monetaryText.test(node.nodeValue||''))node.parentElement?.classList.add('algobot-money-value')});
    }));
    observer.observe(document.body,{subtree:true,childList:true,characterData:true});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
