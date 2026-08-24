/*
 * Production guard for broker payloads consumed by legacy/shared UI.
 * Never fabricates broker credentials or trading values. Missing connection
 * metadata remains explicitly unknown rather than silently becoming demo.
 */
(() => {
  'use strict';
  if (window.__algoBotBrokerPayloadGuard) return;
  window.__algoBotBrokerPayloadGuard = true;

  const originalFetch = window.fetch.bind(window);
  const brokerAccountEndpoint = url => /\/api\/brokers\/accounts(?:\/|\?|$)/.test(url);

  window.fetch = async (input, init) => {
    const response = await originalFetch(input, init);
    const url = typeof input === 'string' ? input : (input?.url || '');
    if (!brokerAccountEndpoint(url) || !response.ok) return response;

    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) return response;

    try {
      const payload = await response.clone().json();
      const normalize = account => {
        if (!account || typeof account !== 'object') return account;
        const copy = { ...account };
        if (!copy.account_type && !copy.credentials?.account_type) copy.account_type = 'unknown';
        if (copy.credentials) {
          const credentials = { ...copy.credentials };
          delete credentials.access_token;
          delete credentials.refresh_token;
          delete credentials.api_key;
          delete credentials.api_secret;
          delete credentials.password;
          delete credentials.client_secret;
          copy.credentials = credentials;
        }
        return copy;
      };
      const normalized = Array.isArray(payload)
        ? payload.map(normalize)
        : Array.isArray(payload?.results)
          ? { ...payload, results: payload.results.map(normalize) }
          : payload?.account
            ? { ...payload, account: normalize(payload.account) }
            : payload;
      const body = JSON.stringify(normalized);
      return new Response(body, {
        status: response.status,
        statusText: response.statusText,
        headers: response.headers
      });
    } catch (_) {
      return response;
    }
  };

  function sanitizeDisabledAccountSwitcher() {
    document.querySelectorAll('[data-account-switch]:disabled').forEach(button => {
      const span = button.querySelector('span:not(.algobot-switch-avatar)');
      if (span) span.textContent = 'Connect another account';
      button.title = 'Connect another broker account before switching.';
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', sanitizeDisabledAccountSwitcher, { once: true });
  else sanitizeDisabledAccountSwitcher();
  new MutationObserver(sanitizeDisabledAccountSwitcher).observe(document.documentElement, { childList: true, subtree: true });
})();
