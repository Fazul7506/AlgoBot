(() => {
  'use strict';
  if (window.__algoBotPositionsPage) return;
  window.__algoBotPositionsPage = true;
  const $ = (selector, root = document) => root.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const state = { rows: [], status: 'loading', meta: null, socket: null, retry: 0, timer: null, accountId: null };
  const list = value => Array.isArray(value) ? value : (Array.isArray(value?.data) ? value.data : (Array.isArray(value?.results) ? value.results : []));
  const money = (value, currency = '') => {
    if (value == null || value === '') return 'Unavailable';
    const n = Number(value);
    if (!Number.isFinite(n)) return 'Unavailable';
    if (typeof window.AlgoBotMoney?.format === 'function') return window.AlgoBotMoney.format(n, currency);
    return (currency ? String(currency) + ' ' : '') + n.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:8});
  };
  const accountId = () => {
    const account = window.AlgoBotBrokerState?.get?.()?.account;
    return account?.id == null ? null : String(account.id);
  };
  function setState(status, message) {
    state.status = status;
    const a = $('[data-page-status]'), b = $('[data-position-state]');
    if (a) a.textContent = message || status;
    if (b) { b.textContent = message || status; b.className = 'positions-state-' + status; }
  }
  function summary() {
    const count = $('[data-record-count]');
    const pnl = $('[data-page-pnl]');
    const updated = $('[data-page-updated]');
    if (count) count.textContent = state.status === 'unavailable' ? 'Unavailable' : String(state.rows.length);
    const known = state.rows.map(r => Number(r.profit)).filter(Number.isFinite);
    const currency = state.rows.find(r => r.currency)?.currency || '';
    if (pnl) pnl.textContent = known.length ? money(known.reduce((a,b)=>a+b,0),currency) : 'Unavailable';
    if (updated) updated.textContent = state.meta?.synchronized_at ? new Date(state.meta.synchronized_at).toLocaleString() : '—';
  }
  function filtered() {
    const q = String($('[data-page-search]')?.value || '').trim().toLowerCase();
    const status = String($('[data-position-status]')?.value || '').toLowerCase();
    const order = String($('[data-position-order]')?.value || 'newest');
    let rows = state.rows.filter(r => (!status || String(r.status || '').toLowerCase() === status) && (!q || [r.symbol,r.contract_id,r.transaction_id,r.contract_type].some(v => String(v ?? '').toLowerCase().includes(q))));
    const value = r => order === 'pnl' || order === '-pnl' ? Number(r.profit) : order === 'stake' ? Number(r.stake) : Date.parse(r.broker_timestamp || r.opened_at || '') || 0;
    const dir = order === 'oldest' || order === '-pnl' ? 1 : -1;
    rows.sort((a,b) => { const av=value(a),bv=value(b); return (Number.isFinite(av)&&Number.isFinite(bv)) ? (av-bv)*dir : 0; });
    return rows;
  }
  function render() {
    const tbody = $('tbody', $('[data-page-table]'));
    if (!tbody) return;
    const rows = filtered();
    if (!rows.length) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="8">' + (state.status === 'loading' ? 'Synchronizing with the broker…' : state.status === 'unavailable' ? 'Broker position data is unavailable.' : state.status === 'stale' ? 'No cached open positions are available.' : 'The broker reports no open positions.') + '</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(r => {
      const pnl = Number(r.profit), cls = Number.isFinite(pnl) ? (pnl > 0 ? 'is-profit' : pnl < 0 ? 'is-loss' : '') : 'is-unknown';
      return '<tr data-position-id="' + esc(r.contract_id) + '" tabindex="0"><td><div class="position-instrument"><strong>' + esc(r.symbol || 'Unknown instrument') + '</strong><small>' + esc(r.display_name || r.contract_type || 'Broker contract') + '</small></div></td><td><div class="position-contract"><strong>' + esc(r.contract_type || 'Unavailable') + '</strong><code>' + esc(r.contract_id) + '</code></div></td><td>' + money(r.stake,r.currency) + '</td><td>' + money(r.entry_price,r.currency) + '</td><td>' + money(r.current_price,r.currency) + '</td><td><span class="position-pnl ' + cls + '">' + (Number.isFinite(pnl) ? money(pnl,r.currency) : 'Unavailable') + '</span></td><td>' + esc(r.expiry_time ? new Date(r.expiry_time).toLocaleString() : 'Unavailable') + '</td><td><span class="position-status">' + esc(r.status || 'unknown') + '</span></td></tr>';
    }).join('');
    rows.forEach(r => {
      const row = [...tbody.querySelectorAll('tr[data-position-id]')].find(el => el.getAttribute('data-position-id') === String(r.contract_id));
      row?.addEventListener('click',() => detail(r));
      row?.addEventListener('keydown',e => { if(e.key === 'Enter' || e.key === ' '){e.preventDefault();detail(r);} });
    });
  }
  function detail(r) {
    const panel=$('[data-position-detail]'), grid=$('[data-position-detail-grid]');
    if(!panel || !grid) return;
    const fields=[['Contract ID',r.contract_id],['Transaction ID',r.transaction_id],['Broker order ID',r.broker_order_id],['Instrument',r.symbol],['Contract type',r.contract_type],['Direction',r.direction],['Stake',money(r.stake,r.currency)],['Entry price',money(r.entry_price,r.currency)],['Current price',money(r.current_price,r.currency)],['Exit price',money(r.exit_price,r.currency)],['Payout',money(r.payout,r.currency)],['P/L',money(r.profit,r.currency)],['P/L %',r.roi == null ? 'Unavailable' : Number(r.roi).toFixed(4) + '%'],['Currency',r.currency],['Status',r.status],['Opened',r.opened_at ? new Date(r.opened_at).toLocaleString() : 'Unavailable'],['Expiry',r.expiry_time ? new Date(r.expiry_time).toLocaleString() : 'Unavailable'],['Closed',r.closed_at ? new Date(r.closed_at).toLocaleString() : 'Unavailable'],['Settlement',r.settlement_time ? new Date(r.settlement_time).toLocaleString() : 'Unavailable'],['Broker timestamp',r.broker_timestamp ? new Date(r.broker_timestamp).toLocaleString() : 'Unavailable']];
    grid.innerHTML=fields.map(x => '<div><dt>' + esc(x[0]) + '</dt><dd>' + esc(x[1]) + '</dd></div>').join('');
    panel.hidden=false;
  }
  async function load() {
    setState('loading','Synchronizing broker positions…');
    try {
      const response=await window.AlgoBotFrontendData.request('/api/positions/open/',{},10000);
      state.rows=list(response); state.meta=response?.meta || null;
      if(response?.status === 'ready') setState('ready','Live broker position data');
      else if(response?.status === 'empty') setState('ready','Broker reports no open positions');
      else if(response?.status === 'stale') setState('stale','Broker unavailable — cached broker data');
      else setState('unavailable','Broker position data unavailable');
      summary(); render();
    } catch(error) {
      state.rows=[]; state.meta=null; setState('unavailable','Broker position data unavailable'); summary(); render();
    }
  }
  function schedule(){ clearTimeout(state.timer); state.timer=setTimeout(load,250); }
  function connect() {
    const protocol=location.protocol === 'https:' ? 'wss' : 'ws';
    const socket=new WebSocket(protocol + '://' + location.host + '/ws/broker/');
    state.socket=socket;
    socket.onopen=() => {
      state.retry=0;
      const id=accountId();
      if(id) socket.send(JSON.stringify({action:'account.switch',account_id:id}));
    };
    socket.onmessage=event => {
      try {
        const message=JSON.parse(event.data), payload=message.payload || {}, eventAccount=payload.account_id == null ? null : String(payload.account_id), current=accountId();
        if(eventAccount && current && eventAccount !== current) return;
        if(['portfolio.update','portfolio.contract','broker.connection','broker.error'].includes(message.type)) schedule();
      } catch(_) {}
    };
    socket.onclose=() => {
      if(state.socket !== socket) return;
      const delay=Math.min(30000,1000 * Math.pow(2,Math.min(state.retry++,5)));
      setTimeout(connect,delay);
    };
  }
  function boot() {
    $('[data-page-search]')?.addEventListener('input',render);
    $('[data-position-status]')?.addEventListener('change',render);
    $('[data-position-order]')?.addEventListener('change',render);
    $('[data-position-refresh]')?.addEventListener('click',load);
    $('[data-position-detail-close]')?.addEventListener('click',() => { $('[data-position-detail]').hidden=true; });
    window.AlgoBotBrokerState?.subscribe?.(() => {
      const next=accountId();
      if(next !== state.accountId) {
        state.accountId=next; schedule();
        if(state.socket?.readyState === WebSocket.OPEN && next) state.socket.send(JSON.stringify({action:'account.switch',account_id:next}));
      }
    });
    state.accountId=accountId(); load(); connect();
  }
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded',boot,{once:true}) : boot();
})();