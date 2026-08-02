// Phase 5 Technical Analysis Engine UI helpers
window.AlgoBotmulti_timeframe = { refresh(){ return fetch('/api/analysis/trend/').then(r=>r.json()).catch(()=>null); } };
