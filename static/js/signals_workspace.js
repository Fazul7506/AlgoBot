(() => {
  "use strict";
  if(window.__algoBotSignalsWorkspace)return; window.__algoBotSignalsWorkspace=true;
  const $=id=>document.getElementById(id);
  const esc=v=>String(v??"—").replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const num=(v,d=5)=>v==null||Number.isNaN(Number(v))?"—":Number(v).toLocaleString(undefined,{maximumFractionDigits:d});
  const pct=v=>v==null||Number.isNaN(Number(v))?"—":Number(v).toFixed(1)+"%";
  const state=v=>String(v??"UNAVAILABLE").replaceAll("_"," ");
  const tone=v=>String(v||"").toUpperCase()==="BUY"?"positive":String(v||"").toUpperCase()==="SELL"?"negative":"neutral";
  const S={rows:[],page:1,pageSize:20};
  async function request(path){
    const timeoutMs=12000;
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),timeoutMs);
    try{
      // Signals is rendered by the canonical Django application. Use the
      // same-origin API route so a cross-origin API/CORS failure cannot leave
      // the workspace stuck in a perpetual loading state.
      const r=await fetch(new URL(path,window.location.origin),{
        method:"GET",
        credentials:"same-origin",
        headers:{Accept:"application/json"},
        signal:controller.signal
      });
      let p={};try{p=await r.json()}catch(_){}
      if(!r.ok)throw new Error(p?.message||p?.detail||p?.error?.detail||"Signals unavailable ("+r.status+")");
      return p;
    }catch(error){
      if(error?.name==="AbortError")throw new Error("Signals request timed out after 12s.");
      throw error;
    }finally{clearTimeout(timer)}
  }
  function set(id,v){const e=$(id);if(e)e.textContent=v==null||v===""?"—":v}
  function filterRows(){
    const q=($("search").value||"").toLowerCase(), symbol=$("symbolFilter").value, direction=$("direction").value, status=$("status").value;
    return S.rows.filter(r=>(!q||[r.symbol,r.display_name,r.strategy,r.lifecycle,r.status].join(" ").toLowerCase().includes(q))&&(!symbol||r.symbol===symbol)&&(!direction||r.direction===direction)&&(!status||r.lifecycle===status));
  }
  function render(){
    const rows=filterRows(), pages=Math.max(1,Math.ceil(rows.length/S.pageSize));S.page=Math.min(S.page,pages);const page=rows.slice((S.page-1)*S.pageSize,S.page*S.pageSize);
    set("pager","Page "+S.page+" of "+pages+" · "+rows.length+" matching");$("prev").disabled=S.page<=1;$("next").disabled=S.page>=pages;
    $("table").innerHTML=page.map(r=>'<tr data-symbol="'+esc(r.symbol)+'"><td><strong>'+esc(r.display_name||r.symbol)+'</strong><small>'+esc(r.symbol)+"</small></td><td>"+esc(r.timeframe)+"</td><td class=""+tone(r.direction)+"">"+esc(r.direction||"WAIT")+"</td><td>"+pct(r.confidence)+"</td><td>"+esc(state(r.lifecycle||r.status))+"</td><td>"+(r.live?.price!=null?num(r.live.price):"—")+"</td><td>"+(r.live?.age_seconds!=null?r.live.age_seconds+"s":"—")+"</td><td><span class="status "+tone(r.direction)+"">"+esc(r.execution_ready?"ACTIONABLE":"REVIEW")+"</span></td></tr>').join("")||'<tr><td colspan="8">No validated research opportunities match these filters.</td></tr>';
    $("table").querySelectorAll("tr[data-symbol]").forEach(tr=>tr.addEventListener("click",()=>focus(S.rows.find(r=>r.symbol===tr.dataset.symbol))));
    const actionable=S.rows.filter(r=>r.execution_ready).length;set("actionable",actionable);set("matched",S.rows.filter(r=>r.analysis_signal_id).length+"/"+S.rows.length);set("count",S.rows.length);focus(page[0]||null);
  }
  function focus(r){
    if(!r){set("focusTitle","Select a signal");set("focusState","WAITING");set("focusDirection","—");set("focusPrice","—");set("focusConfidence","—");$("evidence").innerHTML='<span class="muted">No signal selected.</span>';return}
    set("focusTitle",(r.display_name||r.symbol)+" · "+(r.timeframe||""));set("focusState",state(r.lifecycle||r.status));$("focusState").className="state "+tone(r.direction);set("focusDirection",r.direction||"WAIT");$("focusDirection").className="value "+tone(r.direction);set("focusPrice",r.live?.price!=null?num(r.live.price):"—");set("focusConfidence",pct(r.confidence));set("focusAge",r.live?.age_seconds!=null?r.live.age_seconds+"s":"—");set("focusEntry",num(r.entry_price));set("focusStop",num(r.stop_loss));set("focusTake",num(r.take_profit));set("focusStrategy",(r.strategy||"—")+" v"+(r.strategy_version||"—"));set("focusAccount",r.account_id||"—");set("focusExecution",r.execution_ready?"Execution gate eligible":"Execution not eligible");
    $("evidence").innerHTML=(r.evidence||[]).map(x=>'<span class="tag">'+esc(state(x))+"</span>").join("")||'<span class="muted">No persisted confirmation evidence.</span>';
    $("provenance").innerHTML=Object.entries(r.provenance||{}).map(([k,v])=>'<div class="evidence-row"><span>'+esc(state(k))+"</span><strong>"+esc(v)+"</strong></div>").join("")||'<span class="muted">No provenance available.</span>';
  }
  function populate(){
    const syms=[...new Set(S.rows.map(r=>r.symbol).filter(Boolean))].sort(),statuses=[...new Set(S.rows.map(r=>r.lifecycle).filter(Boolean))].sort();
    $("symbolFilter").innerHTML='<option value="">All instruments</option>'+syms.map(x=>'<option>'+esc(x)+"</option>").join("");
    $("status").innerHTML='<option value="">All lifecycle states</option>'+statuses.map(x=>'<option value="'+esc(x)+'">'+esc(state(x))+"</option>").join("");
  }
  async function scan(){
    $("scan").disabled=true;set("health","SCANNING");try{
      const tf=$("timeframe").value, data=await request("/api/strategy-signals/?limit="+encodeURIComponent($("limit").value)+"&timeframe="+encodeURIComponent(tf));
      if(data.status!=="ok")throw new Error(data.message||"Signal service unavailable");
      S.rows=Array.isArray(data.data)?data.data:[];S.page=1;populate();set("health",state(data.research_state||data.state));set("broker",state(data.broker_state||data.broker_feed_state));set("account",data.account?.id||"—");set("accountType",(data.account?.type||"—")+" · "+(data.account?.currency||""));set("scanTime",new Date().toLocaleTimeString());render();
    }catch(e){S.rows=[];set("health","UNAVAILABLE");set("broker","BROKER UNAVAILABLE");set("scanTime",e.message||"Scan failed");render()}finally{$("scan").disabled=false}
  }
  function boot(){
    $("scan").addEventListener("click",scan);$("refresh").addEventListener("click",scan);$("timeframe").addEventListener("change",scan);$("limit").addEventListener("change",scan);
    ["search","symbolFilter","direction","status"].forEach(id=>$(id).addEventListener("input",()=>{S.page=1;render()}));
    $("prev").addEventListener("click",()=>{if(S.page>1){S.page--;render()}});$("next").addEventListener("click",()=>{S.page++;render()});$("pageSize").addEventListener("change",()=>{S.pageSize=Number($("pageSize").value);S.page=1;render()});
    scan();
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot,{once:true});else boot();
})();