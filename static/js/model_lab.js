(() => {
  const page = document.querySelector('[data-page="core-model-lab"]');
  if (!page) return;
  const esc = v => String(v ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const list = v => Array.isArray(v) ? v : (Array.isArray(v?.results) ? v.results : (Array.isArray(v?.data) ? v.data : []));
  const getJSON = async url => { const r=await fetch(url,{credentials:'same-origin',headers:{Accept:'application/json'}}); const t=await r.text(); let d={}; try{d=t?JSON.parse(t):{};}catch{d={detail:t};} if(!r.ok) throw new Error(d.detail||d.message||`Request failed (${r.status})`); return d; };
  const root = page.querySelector('.model-lab');
  const render = async () => {
    const [models,jobs] = await Promise.allSettled([getJSON('/api/ai/models/'),getJSON('/api/ai/training-jobs/')]);
    const ms=models.status==='fulfilled'?list(models.value):[];
    const js=jobs.status==='fulfilled'?list(jobs.value):[];
    const set=(q,v)=>{const e=root.querySelector(q);if(e)e.textContent=v;};
    set('[data-model-count]',ms.length); set('[data-active-count]',ms.filter(m=>['active','production'].includes(String(m.status||'').toLowerCase())).length); set('[data-job-count]',js.length); set('[data-validated-count]',ms.filter(m=>Number(m.accuracy||0)>0 && Number(m.f1_score||0)>0).length);
    const body=root.querySelector('[data-models]');
    body.innerHTML=ms.length?ms.slice(0,100).map(m=>`<tr><td>${esc(m.name)}</td><td>v${esc(m.version)}</td><td>${esc(m.algorithm)}</td><td><span class="badge">${esc(m.status)}</span></td><td>${Number(m.accuracy||0).toFixed(2)}%</td><td>${Number(m.f1_score||0).toFixed(2)}%</td><td>${Number(m.auc||0).toFixed(2)}%</td></tr>`).join(''):'<tr><td colspan="7">No registered models.</td></tr>';
    const jobsBox=root.querySelector('[data-jobs]');
    jobsBox.innerHTML=js.length?js.slice(0,20).map(j=>`<div class="job"><strong>${esc(j.status)}</strong><div class="muted">${esc(j.started_at||j.completed_at||'Not started')}</div><div>Metrics: ${esc(JSON.stringify(j.metrics||{}))}</div></div>`).join(''):'<div class="muted">No training jobs recorded.</div>';
  };
  root.querySelector('[data-model-train]')?.addEventListener('click',async e=>{const out=root.querySelector('[data-train-result]');e.currentTarget.disabled=true;out.className='result';out.textContent='Starting authenticated training job…';try{const r=await fetch('/api/ai/train/',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','Accept':'application/json','X-CSRFToken:document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)?.[1]||''},body:JSON.stringify({mode:'manual'})});const t=await r.text();let d={};try{d=t?JSON.parse(t):{};}catch{d={detail:t};}if(!r.ok)throw new Error(d.detail||'Training request failed');out.textContent=`Training job created: ${d.id??'accepted'} · status ${d.status??'pending'}`;await render();}catch(err){out.className='result error';out.textContent=err.message;}finally{e.currentTarget.disabled=false;}});
  render().catch(err=>{root.querySelector('[data-models]').innerHTML=`<tr><td colspan="7">AI registry unavailable: ${esc(err.message)}</td></tr>`;});
})();
