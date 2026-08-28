(() => {
  'use strict';
  if (window.__algoBotOrdersPage) return;
  window.__algoBotOrdersPage = true;
  const $ = selector => document.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' })[c]);
  let rows = [];
  const pending = new Set(['draft','validated','queued','sent','accepted']);
  const statusClass = s => String(s || 'unknown').toLowerCase().replace(/[^a-z0-9_-]/g,'');
  function render(message = null, state = 'Ready') {
    const table = $('[data-page-table]'); if (!table) return;
    const status = $('[data-page-status]'); const count = $('[data-record-count]'); const risk = $('[data-page-risk]');
    const pendingNode = $('[data-page-pending]'); const executedNode = $('[data-page-executed]');
    if (status) status.textContent = state;
    if (count) count.textContent = message ? '—' : rows.length;
    if (pendingNode) pendingNode.textContent = message ? '—' : rows.filter(r => pending.has(String(r.status || '').toLowerCase())).length;
    if (executedNode) executedNode.textContent = message ? '—' : rows.filter(r => String(r.status || '').toLowerCase() === 'executed').length;
    if (risk) risk.textContent = message ? '—' : rows.filter(r => ['rejected','failed','cancelled'].includes(String(r.status || '').toLowerCase())).length;
    if (message) { table.querySelector('thead').innerHTML=''; table.querySelector('tbody').innerHTML=`<tr class="empty-row"><td>${esc(message)}</td></tr>`; return; }
    const q = String($('[data-page-search]')?.value || '').trim().toLowerCase();
    const wanted = String($('[data-orders-status]')?.value || '').toLowerCase();
    const filtered = rows.filter(r => { const hay=[r.symbol,r.broker_reference,r.strategy,r.direction,r.status,r.order_type].join(' ').toLowerCase(); return (!q || hay.includes(q)) && (!wanted || String(r.status || '').toLowerCase() === wanted); });
    table.querySelector('thead').innerHTML='<tr><th>Symbol</th><th>Side</th><th>Type</th><th>Stake</th><th>Status</th><th>Broker order</th><th>Created</th><th>Action</th></tr>';
    table.querySelector('tbody').innerHTML=filtered.length ? filtered.map(r=>{const s=String(r.status||'unknown').toLowerCase();const action=s==='failed'?`<button class="btn small" type="button" data-retry="${esc(r.id)}">Retry</button>`:pending.has(s)?`<button class="btn small" type="button" data-cancel="${esc(r.id)}">Cancel</button>`:'';return `<tr><td><strong>${esc(r.symbol||'—')}</strong></td><td>${esc(r.direction||'—')}</td><td>${esc(r.order_type||'—')}</td><td>${esc(r.quantity ?? r.stake ?? '—')}</td><td><span class="order-status ${statusClass(s)}">${esc(r.status||'unknown')}</span></td><td>${esc(r.broker_order_id||r.broker_reference||'Pending/unknown')}</td><td>${esc(r.created_at?new Date(r.created_at).toLocaleString():'—')}</td><td>${action}</td></tr>`;}).join(''):'<tr class="empty-row"><td colspan="8">No orders match the current filters.</td></tr>';
  }
  async function request(url, options={}) { const r=await window.AlgoBotFrontendData.request(url, options, 15000); return r; }
  async function load() { render('Loading authenticated broker orders…','Loading'); try { rows=list(await request('/api/orders/')); render(); } catch (error) { rows=[]; render(`Orders unavailable: ${error?.message || 'The backend did not return an order response.'}`,'Error'); } }
  async function action(url, message) { if(!window.confirm(message)) return; try { await request(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})}); await load(); } catch(e) { window.alert(e?.message || 'Order action failed.'); } }
  function boot() { $('[data-page-search]')?.addEventListener('input',render); $('[data-orders-status]')?.addEventListener('change',render); $('[data-orders-refresh]')?.addEventListener('click',load); $('[data-page-table]')?.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.cancel)action(`/api/orders/${encodeURIComponent(b.dataset.cancel)}/cancel/`,'Cancel this order? The existing execution service will process the cancellation.');if(b.dataset.retry)action(`/api/orders/${encodeURIComponent(b.dataset.retry)}/retry/`,'Queue this failed order for retry?');}); load(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true }); else boot();
})();
