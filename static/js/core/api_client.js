(() => {
  'use strict';

  class APIClient {
    constructor({ baseURL = '', defaultHeaders = {}, timeout = 25000 } = {}) {
      this.baseURL = String(baseURL || '').replace(/\/+$/, '');
      this.defaultHeaders = { Accept: 'application/json', ...defaultHeaders };
      this.timeout = timeout;
    }

    getCsrfToken() {
      return document.querySelector('meta[name="csrf-token"]')?.content || document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || '';
    }

    buildUrl(path) {
      if (!path) return this.baseURL || '/';
      if (/^https?:\/\//i.test(path)) return path;
      const normalizedBase = this.baseURL || '';
      const normalizedPath = path.startsWith('/') ? path : `/${path}`;
      return `${normalizedBase}${normalizedPath}`;
    }

    async request(path, options = {}) {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this.timeout);
      const method = String(options.method || 'GET').toUpperCase();
      const headers = {
        ...this.defaultHeaders,
        ...(options.headers || {}),
      };

      if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && !headers['X-CSRFToken'] && !headers['X-CSRF-Token']) {
        headers['X-CSRFToken'] = this.getCsrfToken();
      }

      const requestOptions = {
        ...options,
        method,
        headers,
        signal: controller.signal,
      };

      try {
        const response = await fetch(this.buildUrl(path), requestOptions);
        const text = await response.text();
        const payload = text ? (() => { try { return JSON.parse(text); } catch (_) { return { detail: text }; } })() : {};

        if (!response.ok) {
          const error = new Error(payload.detail || payload.message || `Request failed (${response.status})`);
          error.status = response.status;
          error.payload = payload;
          throw error;
        }

        return payload;
      } finally {
        clearTimeout(timeoutId);
      }
    }

    get(path, options = {}) {
      return this.request(path, { ...options, method: 'GET' });
    }

    post(path, payload, options = {}) {
      return this.request(path, {
        ...options,
        method: 'POST',
        body: JSON.stringify(payload || {}),
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers || {}),
        },
      });
    }

    put(path, payload, options = {}) {
      return this.request(path, {
        ...options,
        method: 'PUT',
        body: JSON.stringify(payload || {}),
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers || {}),
        },
      });
    }

    delete(path, options = {}) {
      return this.request(path, { ...options, method: 'DELETE' });
    }
  }

  const apiClient = new APIClient({ baseURL: document.querySelector('meta[name="algobot-api-base"]')?.content || '' });
  window.AlgoBotAPI = Object.freeze({ APIClient, apiClient });
})();
