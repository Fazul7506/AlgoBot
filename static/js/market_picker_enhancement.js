/* Shared market-picker presentation: symbols remain values for API/backend use. */
(() => {
  'use strict';
  if (window.__algoBotMarketPickerEnhancement) return;
  window.__algoBotMarketPickerEnhancement = true;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const clean = value => String(value || '').replace(/\s+/g, ' ').replace(/^[\s·|—–:()\-]+|[\s·|—–:()\-]+$/g, '').trim();
  const known = Object.freeze({
    R_10:'Volatility 10 Index',R_25:'Volatility 25 Index',R_50:'Volatility 50 Index',R_75:'Volatility 75 Index',R_100:'Volatility 100 Index',
    BOOM50:'Boom 50 Index',BOOM100:'Boom 100 Index',BOOM150:'Boom 150 Index',BOOM150N:'Boom 150 Index',BOOM200:'Boom 200 Index',BOOM300:'Boom 300 Index',BOOM300N:'Boom 300 Index',BOOM500:'Boom 500 Index',BOOM600:'Boom 600 Index',BOOM900:'Boom 900 Index',BOOM1000:'Boom 1000 Index',
    CRASH50:'Crash 50 Index',CRASH150:'Crash 150 Index',CRASH150N:'Crash 150 Index',CRASH300:'Crash 300 Index',CRASH300N:'Crash 300 Index',CRASH500:'Crash 500 Index',CRASH600:'Crash 600 Index',CRASH900:'Crash 900 Index',CRASH1000:'Crash 1000 Index',
    STPRNG:'Step Index 100',STP100:'Step Index 100',STPRNG2:'Step Index 200',STPRNG3:'Step Index 300',STPRNG4:'Step Index 400',STPRNG5:'Step Index 500',STP200:'Step Index 200',STP300:'Step Index 300',STP400:'Step Index 400',STP500:'Step Index 500',
    JD10:'Jump 10 Index',JD25:'Jump 25 Index',JD50:'Jump 50 Index',JD75:'Jump 75 Index',JD100:'Jump 100 Index',RB100:'Range Break 100 Index',RB200:'Range Break 200 Index',RDBEAR:'Bear Market Index',RDBULL:'Bull Market Index',
    BTCUSD:'BTC/USD',CRYBTCUSD:'BTC/USD',ETHUSD:'ETH/USD',CRYETHUSD:'ETH/USD',LTCUSD:'LTC/USD',XRPUSD:'XRP/USD',BCHUSD:'BCH/USD',DOGEUSD:'DOGE/USD',SOLUSD:'SOL/USD',DOTUSD:'DOT/USD',BNBUSD:'BNB/USD'
  });
  const marketName = option => {
    const symbol = String(option?.value || '').trim();
    let label = clean(option?.textContent || '');
    if (!symbol) return label;
    // Remove only the exact backend symbol from the option label, retaining the readable name.
    const escapedSymbol = symbol.replace(/[.]/g, '\\.');
    label = clean(label.replace(new RegExp(escapedSymbol, 'ig'), ' '));
    if (label && label.toUpperCase() !== symbol.toUpperCase() && label !== 'Market instrument') return label;
    const resolved = window.AlgoBotMarketAssets?.resolve?.({symbol, display_name: label || symbol});
    if (resolved?.status === 'verified' && resolved.asset?.label) return resolved.asset.label;
    const upper = symbol.toUpperCase();
    if (known[upper]) return known[upper];
    const fast = /^1HZ(\d+)V$/.exec(upper); if (fast) return `Volatility ${fast[1]} (1s) Index`;
    const fx = /^(?:FRX)?([A-Z]{3})([A-Z]{3})$/.exec(upper); if (fx) return `${fx[1]}/${fx[2]}`;
    return 'Market instrument';
  };
  const renderIcon = (select, name) => {
    const symbol = select.value;
    const row = {symbol, display_name: name};
    return window.AlgoBotMarketAssets?.renderIcon?.(row) || '<span class="market-avatar market-avatar-unmapped" aria-hidden="true"><span class="material-symbols-rounded">show_chart</span></span>';
  };
  const marketIcon = item => {
    const symbol = String((typeof item?.symbol === 'object' ? item.symbol.symbol : item?.symbol) || item?.underlying_symbol || item?.code || '');
    const supplied = String(item?.display_name || (typeof item?.symbol === 'object' ? item.symbol.display_name : '') || item?.name || '');
    const name = marketName({value:symbol,textContent:supplied || symbol});
    return window.AlgoBotMarketAssets?.renderIcon?.({...item,symbol,display_name:name}) || '<span class="market-avatar market-avatar-unmapped" aria-hidden="true"><span class="material-symbols-rounded">show_chart</span></span>';
  };
  const ensureIcon = select => {
    let icon = select.parentElement?.querySelector(':scope > .analysis-market-icon, :scope > .terminal-selected-market-icon, :scope > .market-picker-icon');
    if (!icon) {
      const wrap = document.createElement('span');
      wrap.className = 'market-picker-control';
      icon = document.createElement('span'); icon.className = 'market-picker-icon'; icon.setAttribute('aria-hidden', 'true');
      select.parentNode.insertBefore(wrap, select); wrap.append(icon, select);
    }
    const selected = select.selectedOptions?.[0];
    const html = selected && selected.value ? renderIcon(select, marketName(selected)) : '';
    if (icon.innerHTML !== html) icon.innerHTML = html;
  };
  const enhanceDisplay = node => {
    if (!node || !node.isConnected) return;
    const symbol = String(node.dataset.marketSymbol || '');
    const labelNode = node.querySelector('[data-market-display-label]') || node;
    const supplied = String(node.dataset.marketName || labelNode.textContent || '');
    const name = marketName({value:symbol,textContent:supplied || symbol});
    if (labelNode !== node && labelNode.textContent !== name) labelNode.textContent = name;
    let icon = node.querySelector(':scope > .market-display-icon');
    if (!icon) {
      icon = document.createElement('span');
      icon.className = 'market-display-icon';
      icon.setAttribute('aria-hidden', 'true');
      node.insertBefore(icon, node.firstChild);
    }
    const html = marketIcon({symbol,display_name:name});
    if (icon.innerHTML !== html) icon.innerHTML = html;
  };
  const enhance = select => {
    if (!select || !select.isConnected) return;
    const options = [...select.options].filter(option => option.value && option.value.trim());
    if (!options.length) return;
    for (const option of options) {
      const name = marketName(option);
      if (name && option.textContent !== name) option.textContent = name;
    }
    if (!select.dataset.marketPickerBound) {
      select.addEventListener('change', () => ensureIcon(select));
      select.dataset.marketPickerBound = 'true';
    }
    ensureIcon(select);
  };
  const selector = 'select#symbol, select[name="symbol"], select[data-symbol], select[data-ai-symbol], select#symbolFilter, select[data-instrument-symbol], select[data-market-symbol], select[data-history-symbol]';
  const scan = root => {
    if (root?.matches?.(selector)) enhance(root);
    root?.querySelectorAll?.(selector).forEach(enhance);
    if (root?.matches?.('[data-market-display]')) enhanceDisplay(root);
    root?.querySelectorAll?.('[data-market-display]').forEach(enhanceDisplay);
  };
  const start = () => {
    scan(document);
    const observer = new MutationObserver(records => {
      for (const record of records) {
        if (record.type === 'childList') {
          if (record.target.matches?.(selector)) enhance(record.target);
          record.addedNodes.forEach(node => { if (node.nodeType === 1) scan(node); });
        }
      }
    });
    observer.observe(document.getElementById('app-content') || document.body, {subtree:true,childList:true});
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once:true}); else start();
  window.AlgoBotMarketPicker = Object.freeze({marketName, marketIcon, enhance});
})();
