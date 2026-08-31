(() => {
  'use strict';
  if (window.__algoBotApiExplorer) return;
  window.__algoBotApiExplorer = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const api = (url, options = {}) => window.AlgoBotFrontendData.request(url, options, 15000);
  const pretty = value => JSON.stringify(value ?? {}, null, 2);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  }[char]));
  const methodClass = method => String(method || 'get').toLowerCase();

  let spec = null;
  let entries = [];
  let selected = null;
  let lastLoadedAt = null;

  function notice(message, kind = 'info') {
    const element = $('[data-api-notice]');
    if (!element) return;
    element.hidden = false;
    element.dataset.kind = kind;
    element.textContent = message;
  }

  function flatten(documentation) {
    return Object.entries(documentation?.paths || {}).flatMap(([path, methods]) =>
      Object.entries(methods || {})
        .filter(([method]) => ['get', 'post', 'put', 'patch', 'delete', 'options', 'head'].includes(method))
        .map(([method, operation]) => ({
          path,
          method,
          ...(operation || {}),
          parameters: operation?.parameters || [],
          responses: operation?.responses || {}
        }))
    );
  }

  function authFor(operation) {
    if (operation.security !== undefined) {
      if (!operation.security?.length) return 'Public';
      return operation.security.map(item => Object.keys(item || {})).flat().join(', ') || 'Authenticated';
    }
    if (operation.required_scope) return `Scope: ${operation.required_scope}`;
    if (spec?.security?.length) return 'Authenticated';
    if (spec?.authentication?.type) return spec.authentication.type;
    return 'Authenticated';
  }

  function schemaExample(schema) {
    if (!schema) return null;
    if (schema.example !== undefined) return schema.example;
    if (schema.default !== undefined) return schema.default;
    if (schema.enum?.length) return schema.enum[0];
    if (schema.type === 'object' || schema.properties) {
      return Object.fromEntries(Object.entries(schema.properties || {}).map(([key, value]) => [key, schemaExample(value)]));
    }
    if (schema.type === 'array') return [schemaExample(schema.items || { type: 'string' })];
    if (schema.type === 'integer' || schema.type === 'number') return 0;
    if (schema.type === 'boolean') return false;
    return 'string';
  }

  function requestContract(operation) {
    const body = operation.requestBody?.content || {};
    return {
      parameters: operation.parameters || [],
      requestBody: operation.requestBody || null,
      exampleBody: body['application/json']?.example || schemaExample(body['application/json']?.schema) || null
    };
  }

  function responseContract(operation) {
    return Object.fromEntries(Object.entries(operation.responses || {}).map(([status, response]) => [status, {
      description: response?.description || '',
      content: response?.content || {},
      example: response?.content?.['application/json']?.example || schemaExample(response?.content?.['application/json']?.schema) || null
    }]));
  }

  function endpointUrl(operation) {
    const server = spec?.servers?.[0]?.url || '';
    return `${server}${operation.path}`;
  }

  function examples(operation) {
    const url = endpointUrl(operation);
    const authHeader = spec?.authentication?.headers?.[0] || 'X-API-Key';
    const body = requestContract(operation).exampleBody;
    const curlParts = [`curl -X ${operation.method.toUpperCase()} '${url}'`, `-H 'Accept: application/json'`, `-H '${authHeader}: $ALGOBOT_API_KEY'`];
    if (body && ['post', 'put', 'patch'].includes(operation.method)) {
      curlParts.push(`-H 'Content-Type: application/json'`, `-d '${JSON.stringify(body)}'`);
    }
    const python = `import requests\n\nurl = ${JSON.stringify(url)}\nheaders = {${JSON.stringify(authHeader)}: "${'$'}ALGOBOT_API_KEY"}\nresponse = requests.${operation.method}(url, headers=headers${body ? `, json=${JSON.stringify(body)}` : ''})\nprint(response.json())`;
    const javascript = `const response = await fetch(${JSON.stringify(url)}, {\n  method: ${JSON.stringify(operation.method.toUpperCase())},\n  headers: { "${authHeader}": process.env.ALGOBOT_API_KEY, "Accept": "application/json" }${body ? `,\n  body: JSON.stringify(${JSON.stringify(body)})` : ''}\n});\nconsole.log(await response.json());`;
    return { curl: curlParts.join(' '), python, javascript };
  }

  function renderNav() {
    const nav = $('[data-api-nav]');
    const query = $('[data-api-search]')?.value.trim().toLowerCase() || '';
    if (!nav) return;
    const groups = {};
    entries
      .filter(operation => [operation.path, operation.method, operation.summary, operation.description, operation.operationId, operation.required_scope, ...(operation.tags || [])]
        .join(' ').toLowerCase().includes(query))
      .forEach(operation => {
        (operation.tags?.length ? operation.tags : ['General']).forEach(tag => (groups[tag] ||= []).push(operation));
      });

    nav.innerHTML = Object.keys(groups).sort().map(tag => `
      <div class="api-group">
        <h3>${esc(tag)}</h3>
        ${groups[tag].map(operation => `
          <button type="button" class="api-endpoint${selected === operation ? ' active' : ''}" data-index="${entries.indexOf(operation)}">
            <span class="method ${methodClass(operation.method)}">${esc(operation.method.toUpperCase())}</span>
            <code>${esc(operation.path)}</code>
          </button>`).join('')}
      </div>`).join('') || '<p class="api-empty">No endpoints match your search.</p>';

    $$('[data-index]', nav).forEach(button => button.addEventListener('click', () => select(Number(button.dataset.index))));
  }

  function renderCodeExamples(operation) {
    const data = examples(operation);
    const target = $('[data-selected-examples]');
    if (target) target.textContent = pretty(data);
    const curl = $('[data-example-curl]');
    const python = $('[data-example-python]');
    const javascript = $('[data-example-javascript]');
    if (curl) curl.textContent = data.curl;
    if (python) python.textContent = data.python;
    if (javascript) javascript.textContent = data.javascript;
  }

  function select(index) {
    selected = entries[index];
    if (!selected) return;
    const title = $('[data-selected-title]');
    const summary = $('[data-selected-summary]');
    const method = $('[data-selected-method]');
    const path = $('[data-selected-path]');
    const auth = $('[data-selected-auth]');
    const tags = $('[data-selected-tags]');
    const operationId = $('[data-selected-operation]');
    const description = $('[data-selected-description]');
    if (title) title.textContent = selected.summary || selected.operationId || selected.path;
    if (summary) summary.textContent = selected.description || 'No endpoint description has been published yet.';
    if (method) method.textContent = selected.method.toUpperCase();
    if (path) path.textContent = selected.path;
    if (auth) auth.textContent = authFor(selected);
    if (tags) tags.textContent = (selected.tags || ['General']).join(', ');
    if (operationId) operationId.textContent = selected.operationId || '—';
    if (description) description.textContent = selected.description || selected.summary || 'No description available.';
    const request = $('[data-selected-request]');
    const response = $('[data-selected-response]');
    if (request) request.textContent = pretty(requestContract(selected));
    if (response) response.textContent = pretty(responseContract(selected));
    renderCodeExamples(selected);
    const endpointCount = $('[data-endpoint-count]');
    if (endpointCount) endpointCount.textContent = `${entries.length} endpoints`;
    renderNav();
  }

  async function load() {
    try {
      const payload = await api('/api/developer/docs/');
      spec = payload?.openapi ? payload : (payload?.payload?.openapi ? payload.payload : payload);
      entries = flatten(spec);
      lastLoadedAt = new Date();
      const count = $('[data-endpoint-count]');
      const health = $('[data-api-health]');
      if (count) count.textContent = `${entries.length} endpoints`;
      if (health) health.textContent = entries.length ? `Contract online · ${lastLoadedAt.toLocaleTimeString()}` : 'Contract has no published endpoints';
      const version = $('[data-contract-version]');
      if (version) version.textContent = `OpenAPI ${spec?.openapi || 'unknown'} · API ${spec?.info?.version || 'v1'} · ${entries.length} operations`;
      renderNav();
      if (entries.length) select(selected ? entries.indexOf(selected) : 0);
      else notice('The published API contract contains no operations. Add a backend implementation before exposing a developer endpoint.', 'warning');
    } catch (error) {
      const health = $('[data-api-health]');
      if (health) health.textContent = 'API reference unavailable';
      notice(`Unable to load the published API contract: ${error.message}`, 'error');
    }
  }

  function tabs() {
    $$('[data-tab]').forEach(button => button.addEventListener('click', () => {
      $$('[data-tab]').forEach(item => item.classList.toggle('active', item === button));
      $$('[data-panel]').forEach(panel => { panel.hidden = panel.dataset.panel !== button.dataset.tab; });
    }));
  }

  async function boot() {
    if (!$('[data-api-explorer]')) return;
    $('[data-api-search]')?.addEventListener('input', renderNav);
    $('[data-refresh-api]')?.addEventListener('click', load);
    tabs();
    await load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
