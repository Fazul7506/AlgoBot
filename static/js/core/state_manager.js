(() => {
  'use strict';

  class StateManager {
    constructor(initial = {}) {
      this.state = structuredClone ? structuredClone(initial) : JSON.parse(JSON.stringify(initial));
      this.listeners = new Set();
    }

    set(path, value) {
      const keys = path.split('.');
      const next = this.deepClone(this.state);
      let cursor = next;

      for (let index = 0; index < keys.length - 1; index += 1) {
        const key = keys[index];
        if (cursor[key] == null || typeof cursor[key] !== 'object') {
          cursor[key] = {};
        }
        cursor = cursor[key];
      }

      cursor[keys[keys.length - 1]] = value;
      this.state = next;
      this.emit();
      return this.state;
    }

    get(path, fallback = undefined) {
      const keys = path.split('.');
      let value = this.state;
      for (const key of keys) {
        if (value == null || !Object.prototype.hasOwnProperty.call(value, key)) {
          return fallback;
        }
        value = value[key];
      }
      return value;
    }

    subscribe(listener) {
      if (typeof listener !== 'function') return () => {};
      this.listeners.add(listener);
      return () => this.listeners.delete(listener);
    }

    emit() {
      for (const listener of this.listeners) {
        try {
          listener(this.state);
        } catch (error) {
          setTimeout(() => { throw error; }, 0);
        }
      }
    }

    deepClone(value) {
      if (value === null || typeof value !== 'object') return value;
      if (typeof structuredClone === 'function') {
        try {
          return structuredClone(value);
        } catch (_) {
          return JSON.parse(JSON.stringify(value));
        }
      }
      return JSON.parse(JSON.stringify(value));
    }
  }

  window.AlgoBotStateManager = Object.freeze({ StateManager });
})();
