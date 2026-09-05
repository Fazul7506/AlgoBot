(function () {
  'use strict';
  var page = document.querySelector('[data-page="core-model-lab"]');
  if (!page) return;
  var root = page.querySelector('.model-lab');
  if (!root) return;

  function esc(value) {
    return String(value == null ? '—' : value).replace(/[&<>"']/g, function (char) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char];
    });
  }
  function list(value) {
    if (Array.isArray(value)) return value;
    if (value && Array.isArray(value.results)) return value.results;
    if (value && Array.isArray(value.data)) return value.data;
    return [];
  }
  function requestJSON(url, options) {
    return fetch(url, options || {credentials: 'same-origin', headers: {Accept: 'application/json'}}).then(function (response) {
      return response.text().then(function (text) {
        var data = {};
        try { data = text ? JSON.parse(text) : {}; } catch (error) { data = {detail: text}; }
        if (!response.ok) throw new Error(data.detail || data.message || ('Model Lab API request returned HTTP ' + response.status));
        return data;
      });
    });
  }
  function setText(selector, value) {
    var node = root.querySelector(selector);
    if (node) node.textContent = value;
  }
  function render() {
    return Promise.allSettled([
      requestJSON('/api/ai/models/'),
      requestJSON('/api/ai/training-jobs/')
    ]).then(function (results) {
      var models = results[0].status === 'fulfilled' ? list(results[0].value) : [];
      var jobs = results[1].status === 'fulfilled' ? list(results[1].value) : [];
      setText('[data-model-count]', models.length);
      setText('[data-active-count]', models.filter(function (model) { return ['active', 'production'].indexOf(String(model.status || '').toLowerCase()) >= 0; }).length);
      setText('[data-job-count]', jobs.length);
      setText('[data-validated-count]', models.filter(function (model) { return Number(model.accuracy || 0) > 0 && Number(model.f1_score || 0) > 0; }).length);

      var body = root.querySelector('[data-models]');
      if (body) {
        body.innerHTML = models.length ? models.slice(0, 100).map(function (model) {
          return '<tr><td>' + esc(model.name) + '</td><td>v' + esc(model.version) + '</td><td>' + esc(model.algorithm) + '</td><td><span class="badge">' + esc(model.status) + '</span></td><td>' + Number(model.accuracy || 0).toFixed(2) + '%</td><td>' + Number(model.f1_score || 0).toFixed(2) + '%</td><td>' + Number(model.auc || 0).toFixed(2) + '%</td></tr>';
        }).join('') : '<tr><td colspan="7">No registered models.</td></tr>';
      }
      var jobsBox = root.querySelector('[data-jobs]');
      if (jobsBox) {
        jobsBox.innerHTML = jobs.length ? jobs.slice(0, 20).map(function (job) {
          return '<div class="job"><strong>' + esc(job.status) + '</strong><div class="muted">' + esc(job.started_at || job.completed_at || 'Not started') + '</div><div>Metrics: ' + esc(JSON.stringify(job.metrics || {})) + '</div></div>';
        }).join('') : '<div class="muted">No training jobs recorded.</div>';
      }
    });
  }

  var trainButton = root.querySelector('[data-model-train]');
  if (trainButton) {
    trainButton.addEventListener('click', function () {
      var output = root.querySelector('[data-train-result]');
      trainButton.disabled = true;
      if (output) { output.className = 'result'; output.textContent = 'Starting authenticated training job…'; }
      requestJSON('/api/ai/train/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', Accept: 'application/json'},
        body: JSON.stringify({mode: 'manual'})
      }).then(function (data) {
        if (output) output.textContent = 'Training job created: ' + (data.id || 'accepted') + ' · status ' + (data.status || 'pending');
        return render();
      }).catch(function (error) {
        if (output) { output.className = 'result error'; output.textContent = error.message; }
      }).finally(function () { trainButton.disabled = false; });
    });
  }

  render().catch(function (error) {
    var body = root.querySelector('[data-models]');
    if (body) body.innerHTML = '<tr><td colspan="7">AI registry unavailable: ' + esc(error.message) + '</td></tr>';
  });
})();
