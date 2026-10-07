(() => {
  const page = document.querySelector('[data-page="core-model-lab"]');
  if (!page) return;

  const esc = v => String(v ?? '—').replace(/[&<>"']/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  }[c]));

  const list = v => Array.isArray(v)
    ? v
    : (Array.isArray(v?.results) ? v.results : (Array.isArray(v?.data) ? v.data : []));

  const api = (url, options = {}) => {
    if (!window.AlgoBotFrontendData?.request) {
      throw new Error('Authenticated frontend transport is not ready.');
    }
    return window.AlgoBotFrontendData.request(url, options, 10000);
  };

  const root = page.querySelector('.model-lab');
  if (!root) return;

  const render = async () => {
    const [models, jobs] = await Promise.allSettled([
      api('/api/ai/models/'),
      api('/api/ai/training-jobs/')
    ]);
    const ms = models.status === 'fulfilled' ? list(models.value) : [];
    const js = jobs.status === 'fulfilled' ? list(jobs.value) : [];

    const set = (selector, value) => {
      const element = root.querySelector(selector);
      if (element) element.textContent = value;
    };

    set('[data-model-count]', ms.length);
    set('[data-active-count]', ms.filter(m =>
      ['active', 'production'].includes(String(m.status || '').toLowerCase())
    ).length);
    set('[data-job-count]', js.length);
    set('[data-validated-count]', ms.filter(m =>
      Number(m.accuracy || 0) > 0 && Number(m.f1_score || 0) > 0
    ).length);

    const body = root.querySelector('[data-models]');
    if (body) {
      body.innerHTML = ms.length
        ? ms.slice(0, 100).map(m =>
          '<tr><td>' + esc(m.name) + '</td>' +
          '<td>v' + esc(m.version) + '</td>' +
          '<td>' + esc(m.algorithm) + '</td>' +
          '<td><span class="badge">' + esc(m.status) + '</span></td>' +
          '<td>' + Number(m.accuracy || 0).toFixed(2) + '%</td>' +
          '<td>' + Number(m.f1_score || 0).toFixed(2) + '%</td>' +
          '<td>' + Number(m.auc || 0).toFixed(2) + '%</td></tr>'
        ).join('')
        : '<tr><td colspan="7">No registered models.</td></tr>';
    }

    const jobsBox = root.querySelector('[data-jobs]');
    if (jobsBox) {
      jobsBox.innerHTML = js.length
        ? js.slice(0, 20).map(j =>
          '<div class="job"><strong>' + esc(j.status) + '</strong>' +
          '<div class="muted">' + esc(j.started_at || j.completed_at || 'Not started') + '</div>' +
          '<div>Metrics: ' + esc(JSON.stringify(j.metrics || {})) + '</div></div>'
        ).join('')
        : '<div class="muted">No training jobs recorded.</div>';
    }
  };

  root.querySelector('[data-model-train]')?.addEventListener('click', async event => {
    const output = root.querySelector('[data-train-result]');
    const button = event.currentTarget;
    if (!output) return;

    button.disabled = true;
    output.className = 'result';
    output.textContent = 'Starting authenticated training job…';

    try {
      const data = await api('/api/ai/train/', {
        method: 'POST',
        body: JSON.stringify({ mode: 'manual' }),
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' }
      });
      output.textContent =
        'Training job created: ' + (data.id ?? 'accepted') +
        ' · status ' + (data.status ?? 'pending');
      await render();
    } catch (error) {
      output.className = 'result error';
      output.textContent = error.message || 'Training request failed.';
    } finally {
      button.disabled = false;
    }
  });

  render().catch(error => {
    const body = root.querySelector('[data-models]');
    if (body) {
      body.innerHTML =
        '<tr><td colspan="7">AI registry unavailable: ' +
        esc(error.message) + '</td></tr>';
    }
  });
})();
