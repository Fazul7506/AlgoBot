/* Global anchored select menus. Native selects remain the form/API source of truth;
   this layer replaces the platform picker UI so Android never opens a modal selector. */
(() => {
  'use strict';
  if (window.__algoBotAnchoredSelects) return;
  window.__algoBotAnchoredSelects = true;

  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const MARKET_SELECTOR = 'select#symbol,select[name="symbol"],select[data-symbol],select[data-ai-symbol],select#symbolFilter,select[data-instrument-symbol],select[data-market-symbol],select[data-history-symbol],select[data-scanner-market],select[data-market-filter],select[data-market]';
  // Instrument detection must be based on explicit market-control semantics, not option values.
  // Country codes (e.g. EUR, GBP, XAU-like codes) can resemble symbols and must never
  // cause country/profile dropdowns to inherit market search placeholders or ticker badges.
  const isCountryOrPhoneSelect = select => select.id === 'phone_country_code' || select.matches('[data-country-select],#country,#profile-country,[autocomplete="country-name"]');
  const isInstrumentSelect = select => !isCountryOrPhoneSelect(select) && (select.matches(MARKET_SELECTOR) || select.dataset.abSelectType === 'instrument');
  const optionLabel = option => String(option?.textContent || option?.label || option?.value || '').replace(/\s+/g, ' ').trim();
  const iconFor = (select, option) => {
    if (!option || !option.value) return '<span class="ab-select-option-icon ab-select-option-icon--empty" aria-hidden="true"></span>';
    if (isCountryOrPhoneSelect(select)) return '<span class="ab-select-option-icon ab-select-option-icon--country" aria-hidden="true"></span>';
    if (isInstrumentSelect(select)) {
      const row = {symbol: option.value, display_name: optionLabel(option) || option.value};
      const official = window.AlgoBotMarketAssets?.renderIcon?.(row);
      if (official) return '<span class="ab-select-option-icon ab-select-option-icon--market" aria-hidden="true">' + official + '</span>';
      // Missing market artwork must never become a generated ticker-letter badge.
      return '<span class="ab-select-option-icon ab-select-option-icon--market-fallback" aria-hidden="true"><span class="material-symbols-rounded">show_chart</span></span>';
    }
    return '<span class="ab-select-option-icon" aria-hidden="true"><span class="material-symbols-rounded">check</span></span>';
  };
  // Only leave intentionally hidden synchronization selects native; all visible single-selects
  // use this anchored menu, including controls previously opted out with data-native-select.
  const allSelects = 'select:not([multiple]):not([size]):not([hidden]):not([aria-hidden="true"]):not(.mc-visually-hidden):not([data-ab-select-enhanced]),select[size="1"]:not([multiple]):not([hidden]):not([aria-hidden="true"]):not(.mc-visually-hidden):not([data-ab-select-enhanced])';
  const isHiddenSyncSelect = select => select.multiple || select.size > 1 || select.hidden ||
    select.getAttribute('aria-hidden') === 'true' || select.classList.contains('mc-visually-hidden') ||
    (select.dataset.nativeSelect === 'true' && (select.offsetParent === null || getComputedStyle(select).display === 'none'));
  let openRoot = null;

  function close(root, restoreFocus = false) {
    if (!root) return;
    const button = root.querySelector('.ab-select-trigger');
    const menu = root.querySelector('.ab-select-menu');
    if (menu) menu.hidden = true;
    if (button) button.setAttribute('aria-expanded', 'false');
    root.classList.remove('is-open');
    if (openRoot === root) openRoot = null;
    if (restoreFocus) button?.focus();
  }

  function selectedOption(select) {
    return select.selectedOptions?.[0] || [...select.options].find(option => option.value === select.value) || null;
  }

  function refresh(select) {
    const root = select.__abSelectRoot;
    if (!root) return;
    const button = root.querySelector('.ab-select-trigger');
    const current = selectedOption(select);
    const label = root.querySelector('.ab-select-value');
    const icon = root.querySelector('.ab-select-current-icon');
    if (label) {
      if (select.id === 'phone_country_code' && current) {
        const iso = current.dataset.iso || '';
        const flag = iso ? String.fromCodePoint(...iso.toUpperCase().split('').map(ch => 127397 + ch.charCodeAt(0))) : '';
        label.textContent = (flag ? flag + ' ' : '') + current.value;
      } else {
        label.textContent = current ? optionLabel(current) : (select.dataset.placeholder || 'Select an option');
      }
    }
    if (icon) icon.innerHTML = select.id === 'phone_country_code' ? '' : iconFor(select, current);
    if (button) {
      button.disabled = select.disabled;
      button.setAttribute('aria-expanded', String(!root.querySelector('.ab-select-menu').hidden));
      button.setAttribute('aria-required', String(select.dataset.abRequired === 'true'));
      button.setAttribute('aria-invalid', select.dataset.abInvalid === 'true' ? 'true' : 'false');
      button.title = current ? optionLabel(current) : '';
    }
    const menu = root.querySelector('.ab-select-menu');
    const search = root.querySelector('.ab-select-search');
    const keepSearch = search?.value || '';
    if (!menu) return;
    const options = [...select.options];
    // Search is opt-in, not automatically injected into every long dropdown.
    // Keep it for instruments and explicitly searchable country/phone selectors.
    const hasSearch = !isCountryOrPhoneSelect(select) && (select.dataset.abSearchable === 'true' || isInstrumentSelect(select));
    if (search) {
      search.hidden = !hasSearch;
      if (!hasSearch) search.value = '';
      else search.value = keepSearch;
    }
    const list = root.querySelector('.ab-select-options');
    list.innerHTML = '';
    let currentGroup = null;
    options.forEach((option, index) => {
      if (option.parentElement?.tagName === 'OPTGROUP' && option.parentElement.label !== currentGroup) {
        currentGroup = option.parentElement.label;
        const group = document.createElement('div');
        group.className = 'ab-select-group-label';
        group.setAttribute('role', 'presentation');
        group.textContent = currentGroup;
        list.appendChild(group);
      }
      if (option.hidden) return;
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'ab-select-option';
      item.setAttribute('role', 'option');
      item.dataset.value = option.value;
      item.dataset.index = String(index);
      item.setAttribute('aria-selected', String(option.value === select.value));
      item.disabled = option.disabled || option.parentElement?.disabled || select.disabled;
      item.innerHTML = iconFor(select, option) + '<span class="ab-select-option-label">' + esc(optionLabel(option)) + '</span>' +
        (option.value === select.value ? '<span class="material-symbols-rounded ab-select-check" aria-hidden="true">check</span>' : '');
      item.addEventListener('click', () => choose(select, option));
      item.addEventListener('keydown', event => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault();
          const enabled = [...list.querySelectorAll('.ab-select-option:not(:disabled):not([hidden])')];
          const pos = enabled.indexOf(item);
          enabled[Math.max(0, Math.min(enabled.length - 1, pos + (event.key === 'ArrowDown' ? 1 : -1)))]?.focus();
        } else if (event.key === 'Escape') { event.preventDefault(); close(root, true); }
      });
      list.appendChild(item);
    });
    if (search && keepSearch) filterOptions(root, keepSearch);
  }

  function filterOptions(root, query) {
    const q = String(query || '').trim().toLocaleLowerCase();
    root.querySelectorAll('.ab-select-option').forEach(item => {
      item.hidden = !!q && !item.textContent.toLocaleLowerCase().includes(q);
    });
    root.querySelectorAll('.ab-select-group-label').forEach(group => {
      let next = group.nextElementSibling;
      let any = false;
      while (next && !next.classList.contains('ab-select-group-label')) {
        if (next.classList.contains('ab-select-option') && !next.hidden) any = true;
        next = next.nextElementSibling;
      }
      group.hidden = !!q && !any;
    });
  }

  function choose(select, option) {
    if (!option || option.disabled || select.disabled) return;
    const previous = select.value;
    select.value = option.value;
    select.dataset.abInvalid = 'false';
    if (previous !== select.value) {
      select.dispatchEvent(new Event('input', {bubbles:true}));
      select.dispatchEvent(new Event('change', {bubbles:true}));
    }
    refresh(select);
    close(select.__abSelectRoot);
    select.__abSelectRoot?.querySelector('.ab-select-trigger')?.focus();
  }

  function open(root) {
    if (root.querySelector('.ab-select-trigger')?.disabled) return;
    if (openRoot && openRoot !== root) close(openRoot);
    const menu = root.querySelector('.ab-select-menu');
    const button = root.querySelector('.ab-select-trigger');
    if (!menu || !button) return;
    menu.classList.remove('ab-select-menu--up');
    const rect = root.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;
    if (spaceBelow < 260 && spaceAbove > spaceBelow) menu.classList.add('ab-select-menu--up');
    menu.hidden = false;
    root.classList.add('is-open');
    button.setAttribute('aria-expanded', 'true');
    openRoot = root;
    const search = root.querySelector('.ab-select-search');
    if (search && !search.hidden) { search.focus(); search.select(); }
    else {
      const active = root.querySelector('.ab-select-option[aria-selected="true"]:not(:disabled)') ||
        root.querySelector('.ab-select-option:not(:disabled)');
      active?.scrollIntoView({block:'nearest'});
      button.focus();
    }
  }

  function enhance(select) {
    if (!select || select.dataset.abSelectEnhanced === 'true' || isHiddenSyncSelect(select) || !select.parentNode) return;
    select.dataset.abSelectEnhanced = 'true';
    if (select.required) {
      select.dataset.abRequired = 'true';
      select.required = false;
    }
    const instrumentSelect = isInstrumentSelect(select);
    if (instrumentSelect) {
      select.parentElement?.querySelectorAll(':scope > .market-picker-icon, :scope > .terminal-selected-market-icon, :scope > .analysis-market-icon').forEach(icon => { icon.hidden = true; });
    }
    const root = document.createElement('div');
    root.className = 'ab-select-root' + (instrumentSelect ? ' ab-select-root--instrument' : '');
    root.dataset.abSelectRoot = '';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'ab-select-trigger';
    button.setAttribute('role', 'combobox');
    button.setAttribute('aria-haspopup', 'listbox');
    button.setAttribute('aria-expanded', 'false');
    button.setAttribute('aria-label', select.getAttribute('aria-label') || select.labels?.[0]?.textContent?.trim() || 'Select an option');
    const currentIcon = document.createElement('span');
    currentIcon.className = 'ab-select-current-icon';
    currentIcon.setAttribute('aria-hidden', 'true');
    const value = document.createElement('span');
    value.className = 'ab-select-value';
    const chevron = document.createElement('span');
    chevron.className = 'material-symbols-rounded ab-select-chevron';
    chevron.setAttribute('aria-hidden', 'true');
    chevron.textContent = 'expand_more';
    button.append(currentIcon, value, chevron);
    const menu = document.createElement('div');
    menu.className = 'ab-select-menu';
    menu.hidden = true;
    menu.setAttribute('role', 'presentation');
    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'ab-select-search';
    search.placeholder = 'Search instruments…';
    search.setAttribute('aria-label', search.placeholder);
    search.hidden = true;
    const list = document.createElement('div');
    list.className = 'ab-select-options';
    list.id = 'ab-select-list-' + Math.random().toString(36).slice(2, 10);
    list.setAttribute('role', 'listbox');
    button.setAttribute('aria-controls', list.id);
    menu.append(search, list);
    select.classList.add('ab-select-native');
    select.tabIndex = -1;
    select.insertAdjacentElement('beforebegin', root);
    root.append(button, menu, select);
    select.__abSelectRoot = root;
    button.addEventListener('click', () => menu.hidden ? open(root) : close(root));
    [...(select.labels || [])].forEach(label => label.addEventListener('click', event => {
      if (event.target.closest('.ab-select-root')) return;
      event.preventDefault();
      button.focus();
      open(root);
    }));
    button.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
        event.preventDefault(); open(root);
        const active = root.querySelector('.ab-select-option[aria-selected="true"]:not(:disabled)') || root.querySelector('.ab-select-option:not(:disabled)');
        active?.focus();
      } else if (event.key === 'Escape') close(root);
    });
    search.addEventListener('input', () => filterOptions(root, search.value));
    search.addEventListener('keydown', event => {
      if (event.key === 'Escape') { event.preventDefault(); close(root, true); }
      if (event.key === 'ArrowDown') { event.preventDefault(); root.querySelector('.ab-select-option:not(:disabled):not([hidden])')?.focus(); }
    });
    select.addEventListener('change', () => refresh(select));
    select.addEventListener('input', () => refresh(select));
    const form = select.form;
    if (form && select.dataset.abRequired === 'true') {
      form.addEventListener('reset', () => setTimeout(() => refresh(select), 0));
    }
    refresh(select);
  }

  document.addEventListener('click', event => {
    if (openRoot && !openRoot.contains(event.target)) close(openRoot);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && openRoot) close(openRoot, true);
  });
  document.addEventListener('submit', event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const invalid = [...form.querySelectorAll('select[data-ab-required="true"]')].find(select => !select.disabled && !select.value);
    if (invalid) {
      event.preventDefault();
      invalid.dataset.abInvalid = 'true';
      refresh(invalid);
      invalid.__abSelectRoot?.querySelector('.ab-select-trigger')?.focus();
      invalid.__abSelectRoot?.querySelector('.ab-select-trigger')?.setAttribute('aria-describedby', invalid.id ? invalid.id + '-error' : '');
    }
  }, true);

  function scan(root = document) {
    if (root.matches?.(allSelects)) enhance(root);
    root.querySelectorAll?.(allSelects).forEach(enhance);
  }
  const start = () => {
    scan();
    const observer = new MutationObserver(records => {
      records.forEach(record => {
        record.addedNodes.forEach(node => { if (node.nodeType === 1) scan(node); });
        if (record.type === 'childList') {
          const select = record.target instanceof HTMLSelectElement ? record.target : record.target.closest?.('select');
          if (select) refresh(select);
        }
      });
    });
    observer.observe(document.getElementById('app-content') || document.body, {
      subtree:true, childList:true, attributes:true,
      attributeFilter:['disabled','required','aria-label','data-placeholder','hidden','label','value']
    });
    document.querySelectorAll('form').forEach(form => form.addEventListener('reset', () => setTimeout(() => form.querySelectorAll('select[data-ab-select-enhanced="true"]').forEach(refresh), 0)));
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once:true}); else start();
  window.AlgoBotAnchoredSelects = Object.freeze({enhance, refresh, closeAll:() => close(openRoot)});
})();
