const initializePreferences = () => {
  const root = document.querySelector('[data-settings-page]');
  if (!root) return;
  const form = root.querySelector('[data-settings-form]');
  const status = root.querySelector('[data-settings-status]');
  const message = root.querySelector('[data-settings-message]');
  const saveButton = root.querySelector('[data-save-settings]');
  const field = name => form.elements.namedItem(name);
  let lastSavedFormState = null;
  const captureFormState = () => [...form.elements].filter(control => control.name).map(control => ({name:control.name,type:control.type,value:control.value,checked:control.checked}));
  const restoreFormState = state => {
    if (!state) return;
    state.forEach(saved => {
      const control = [...form.elements].find(item => item.name === saved.name && item.type === saved.type && item.value === saved.value);
      if (!control) return;
      if (control.type === 'checkbox' || control.type === 'radio') control.checked = saved.checked;
      else if (control.type !== 'submit' && control.type !== 'button') control.value = saved.value;
    });
    applyAppearance({theme:form.querySelector('input[name="theme"]:checked')?.value || 'dark',density:form.querySelector('input[name="density"]:checked')?.value || 'default',accent:form.querySelector('input[name="accent"]:checked')?.value || 'cyan'});
  };
  const setRadio = (name, value) => { const input = form.querySelector('input[name="' + name + '"][value="' + value + '"]'); if (input) input.checked = true; };
  const check = (name, value) => { if (field(name)) field(name).checked = Boolean(value); };
  const request = async (method, body) => {
    const client = window.AlgoBotFrontendData;
    if (!client?.request) throw new Error('The shared API client is unavailable. Refresh the page and try again.');
    return client.request('/api/settings/', {
      method,
      credentials: 'include',
      ...(body ? {headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {}),
    }, 25000);
  };
  const applyAppearance = (prefs) => {
    const html = document.documentElement;
    const storedTheme = (() => { try { return localStorage.getItem('algobot-theme-preference') || localStorage.getItem('algobot-theme'); } catch (_) { return ''; } })();
    const existingTheme = ['light','dark','system'].includes(html.dataset.themePreference) ? html.dataset.themePreference : storedTheme;
    const preferenceTheme = ['light','dark','system'].includes(prefs.theme) ? prefs.theme : (['light','dark','system'].includes(existingTheme) ? existingTheme : 'dark');
    html.dataset.themePreference = preferenceTheme;
    try { localStorage.setItem('algobot-theme-preference', preferenceTheme); } catch (_) {}
    let theme = preferenceTheme;
    if (theme === 'system') {
      try { localStorage.removeItem('algobot-theme'); } catch (_) {}
      theme = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    } else {
      try { localStorage.setItem('algobot-theme', theme); } catch (_) {}
    }
    html.dataset.theme = theme;
    html.dataset.density = prefs.density || 'default';
    html.dataset.accent = prefs.accent || 'cyan';
    html.dataset.layout = prefs.layout || 'classic';
    html.dataset.chartPosition = prefs.chart_position || 'right';
    html.dataset.autoRefresh = prefs.auto_refresh_interval || 'realtime';
    html.dataset.refreshFrequency = prefs.refresh_frequency || '1m';
    html.dataset.defaultPage = prefs.default_page || 'dashboard';
  };
  async function load() {
    const data = await request('GET');
    const profile = data.profile || {};
    const prefs = profile.account_preferences || {};
    const storedTheme = (() => { try { return localStorage.getItem('algobot-theme-preference') || localStorage.getItem('algobot-theme'); } catch (_) { return ''; } })();
    const effectiveTheme = ['light','dark','system'].includes(prefs.theme) ? prefs.theme
      : (['light','dark','system'].includes(document.documentElement.dataset.themePreference) ? document.documentElement.dataset.themePreference
      : (['light','dark','system'].includes(storedTheme) ? storedTheme : 'dark'));
    setRadio('theme', effectiveTheme);
    setRadio('density', prefs.density || 'default');
    setRadio('accent', prefs.accent || 'cyan');
    ['layout','chart_position','default_page','auto_refresh_interval','refresh_frequency'].forEach(name => { if (field(name)) field(name).value = prefs[name] || ({layout:'classic',chart_position:'right',default_page:'dashboard',auto_refresh_interval:'realtime',refresh_frequency:'1m'}[name]); });
    const categories = prefs.notification_categories || {};
    ['trade_alerts','price_alerts','market_news','system_updates'].forEach(name => check(name, categories[name] !== false));
    check('security_alerts', true);
    check('notifications_enabled', profile.notifications_enabled);
    check('email_notifications_enabled', profile.email_notifications_enabled);
    check('telegram_notifications_enabled', profile.telegram_notifications_enabled);
    if (field('timezone')) {
      const zone = profile.timezone || 'UTC';
      if (![...field('timezone').options].some(option => option.value === zone)) field('timezone').add(new Option(zone, zone));
      field('timezone').value = zone;
    }
    const username = data.user?.username || 'Your AlgoBot account';
    const email = data.user?.email || 'No login email configured';
    root.querySelector('[data-preferences-user]').textContent = username;
    root.querySelector('[data-preferences-email]').textContent = email;
    const resolvedPreferences = {...prefs, theme: effectiveTheme};
    applyAppearance(resolvedPreferences);
    document.dispatchEvent(new CustomEvent('algobot:preferences-loaded', {detail: resolvedPreferences}));
    lastSavedFormState = captureFormState();
    status.textContent = 'Preferences loaded';
    status.classList.remove('account-state--warn','account-state--bad'); status.classList.add('account-state--good');
    saveButton.disabled = false;
  }
  form.addEventListener('change', event => {
    const target = event.target;
    if (target.name === 'theme' || target.name === 'density' || target.name === 'accent') {
      applyAppearance({theme:field('theme').value,density:field('density').value,accent:field('accent').value});
    }
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    saveButton.disabled = true; message.textContent = 'Saving preferences…';
    const preferences = {
      theme: form.querySelector('input[name="theme"]:checked')?.value || 'dark',
      density: form.querySelector('input[name="density"]:checked')?.value || 'default',
      accent: form.querySelector('input[name="accent"]:checked')?.value || 'cyan',
      layout: field('layout').value,
      chart_position: field('chart_position').value,
      default_page: field('default_page').value,
      auto_refresh_interval: field('auto_refresh_interval').value,
      refresh_frequency: field('refresh_frequency').value,
      notification_categories: {
        trade_alerts: field('trade_alerts').checked,
        price_alerts: field('price_alerts').checked,
        market_news: field('market_news').checked,
        system_updates: field('system_updates').checked,
        security_alerts: true
      }
    };
    const profile = {
      timezone: field('timezone').value,
      notifications_enabled: field('notifications_enabled').checked,
      email_notifications_enabled: field('email_notifications_enabled').checked,
      telegram_notifications_enabled: field('telegram_notifications_enabled').checked
    };
    const submittedFormState = captureFormState();
    // Lock the controls while this request is in flight. Otherwise users can
    // change values after the payload is built and see unsaved values presented
    // as though they were persisted by this request.
    const controls = [...form.elements].filter(control => control !== saveButton);
    controls.forEach(control => { control.disabled = true; });
    try {
      const data = await request('PATCH', {profile, preferences});
      applyAppearance(preferences);
      document.dispatchEvent(new CustomEvent('algobot:preferences-loaded', {detail: preferences}));
      lastSavedFormState = submittedFormState;
      message.textContent = data.message || 'Preferences saved.';
      status.textContent = 'Preferences saved';
      status.classList.remove('account-state--warn','account-state--bad'); status.classList.add('account-state--good');
    } catch (error) {
      restoreFormState(lastSavedFormState);
      message.textContent = error.message || 'Could not save preferences. Your previous saved settings have been restored.';
      status.textContent = 'Save failed';
      status.classList.remove('account-state--good'); status.classList.add('account-state--bad');
    } finally {
      controls.forEach(control => { control.disabled = false; });
      saveButton.disabled = false;
    }
  });
  load().catch(error => {
    status.textContent = 'Could not load preferences'; status.classList.add('account-state--bad');
    message.textContent = error.message || 'Refresh the page to try again.';
    saveButton.disabled = true;
  });
};
// This inline block is parsed before the base template's deferred shared API scripts.
// Wait until deferred scripts have executed so AlgoBotFrontendData is available.
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializePreferences, {once: true});
} else {
  initializePreferences();
}
