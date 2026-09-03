(() => {
  'use strict';

  const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

  function readCookie(name) {
    const prefix = `${name}=`;
    return document.cookie.split(';').map(v => v.trim()).find(v => v.startsWith(prefix))?.slice(prefix.length) || '';
  }

  function csrfToken() {
    const cookieToken = readCookie('csrftoken');
    if (cookieToken) return decodeURIComponent(cookieToken);
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
  }

  class APIClient {
    constructor({ baseURL = '', defaultHeaders = {}, timeout = 25000 } = {}) {
      this.baseURL = String(baseURL || '').replace(/\/+$/, '');
      this.defaultHeaders = { Accept: 'application/json', ...defaultHeaders };
      this.timeout = timeout;
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
      if (!SAFE_METHODS.has(method)) {
        const token = csrfToken();
        if (token && !Object.keys(headers).some(key => key.toLowerCase() === 'x-csrftoken')) {
          headers['X-CSRFToken'] = token;
        }
      }

      const requestOptions = {
        ...options,
        method,
        headers,
        credentials: options.credentials || 'include',
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
  window.AlgoBotAPI = Object.freeze({ APIClient, apiClient, csrfToken });
})();
