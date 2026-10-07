(() => {
  "use strict";
  if (window.__algoBotAnalysisWorkspace) return;
  window.__algoBotAnalysisWorkspace = true;
  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? "—").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const num = (v,d=5) => v==null || Number.isNaN(Number(v)) ? "—" : Number(v).toLocaleString(undefined,{maximumFractionDigits:d});
  const pct = v => v==null || Number.isNaN(Number(v)) ? "—" : Number(v).toFixed(1)+"%";
  const money = (v,c) => v==null || v==="" ? "—" : (c ? c+" " : "")+Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
  const state = v => String(v ?? "UNAVAILABLE").replaceAll("_"," ");
  const tone = v => ["BUY","BULLISH","STRONG BULLISH"].includes(String(v||"").toUpperCase()) ? "positive" : ["SELL","BEARISH","STRONG BEARISH"].includes(String(v||"").toUpperCase()) ? "negative" : "neutral";
  const A = {markets:[],data:null,contract:null,timer:null};

  async function request(path, options={}) {
    return window.AlgoBotFrontendData.request(path, options, 12000);
  }
  function set(id,v){const e=$(id);if(e)e.textContent=v==null||v===""?"—":v}
  function list(id,items,fn,empty="No observed evidence."){const e=$(id);if(e)e.innerHTML=items?.length?items.map(fn).join(""):'<span class="muted">'+esc(empty)+"</span>"}
  function setHealth(ok,text){$("aFeed").className="health-dot "+(ok?"live":"");set("aFeedText",text)}

  function drawChart(candles){
    const canvas=$("analysisChart"), empty=$("chartEmpty");
    if(!canvas)return;
    if(!candles?.length){canvas.hidden=true;empty.hidden=false;return}
    canvas.hidden=false;empty.hidden=true;
    const box=canvas.getBoundingClientRect(), q=window.devicePixelRatio||1, w=Math.max(320,box.width), h=Math.max(280,box.height);
    canvas.width=w*q;canvas.height=h*q;const ctx=canvas.getContext("2d");ctx.setTransform(q,0,0,q,0,0);ctx.clearRect(0,0,w,h);
    const hi=Math.max(...candles.map(x=>Number(x.high))), lo=Math.min(...candles.map(x=>Number(x.low))), span=hi-lo||1;
    const y=v=>h-24-(Number(v)-lo)/span*(h-48), step=w/Math.max(1,candles.length-1);
    ctx.strokeStyle="rgba(148,163,184,.15)"; for(let i=1;i<6;i++){ctx.beginPath();ctx.moveTo(0,h*i/6);ctx.lineTo(w,h*i/6);ctx.stroke()}
    candles.forEach((x,i)=>{const xx=i*step,up=Number(x.close)>=Number(x.open);ctx.strokeStyle=up?"#22c55e":"#ef4444";ctx.beginPath();ctx.moveTo(xx,y(x.high));ctx.lineTo(xx,y(x.low));ctx.stroke();const top=Math.min(y(x.open),y(x.close)), bh=Math.max(1,Math.abs(y(x.close)-y(x.open)));ctx.fillStyle=ctx.strokeStyle;ctx.fillRect(xx-2,top,4,bh)});
  }

  function render(d){
    A.data=d;
    const gate=d.execution_gate||{}, ai=d.ai||{}, layers=d.analysis_layers||{}, conf=d.confluence||{}, acct=d.account_context||{};
    set("aResearchState",state(d.research_state)); set("aBrokerState",state(d.broker_state)); set("aSymbol",d.symbol); set("aTf",d.timeframe); set("aPrice",num(d.price)); set("aSignal",d.signal||"NO TRADE"); $("aSignal").className="value "+tone(d.signal);
    set("aTechnical",d.score!=null?num(d.score,1)+"/100":"—"); set("aConfidence",pct(d.confidence)); set("aRegime",d.volatility_regime); set("aFresh",d.data_provenance?.fresh?"FRESH":"STALE");
    setHealth(Boolean(d.data_provenance?.fresh && d.live_quote?.fresh),d.live_quote?.fresh?"DERIV LIVE":"DATA NOT FRESH");
    set("marketState",state(layers.market_data?.state)); set("marketSource",layers.market_data?.source); set("marketAge",d.data_provenance?.age_seconds!=null?d.data_provenance.age_seconds+"s":"—"); set("candleCount",d.candles);
    set("trendState",layers.technical?.structure||d.structure); set("trendScore",layers.technical?.score!=null?num(layers.technical.score,1)+"/100":"—"); set("momentumState",d.indicators?.rsi14!=null?"RSI "+num(d.indicators.rsi14,1):"—"); set("volatilityState",d.volatility_regime);
    set("strategyState",state(layers.strategy?.state)); set("strategyDirection",layers.strategy?.direction||"WAIT"); set("strategyEvidence",(layers.strategy?.evidence||[]).join(" · ")||"No persisted strategy evidence");
    set("aiState",state(layers.ai?.state)); set("aiDecision",layers.ai?.decision||"UNAVAILABLE"); set("aiConfidence",pct(layers.ai?.confidence)); set("aiModels",layers.ai?.models_used?String(layers.ai.models_used):"0"); set("aiAgreement",layers.ai?.agreement!=null?pct(Number(layers.ai.agreement)*100):"—");
    set("confluenceState",state(conf.state)); set("confluenceDirection",conf.direction||"WAIT"); set("confluenceScore",conf.score!=null?num(conf.score,1)+"/100":"—");
    list("confluenceEvidence", conf.evidence, e => { const cls = e.passed ? "pass" : "fail"; const label = e.passed ? "PASS" : "WAIT"; return '<div class="evidence-row"><span>' + esc(e.layer) + '</span><strong>' + esc(e.condition) + '</strong><b class="' + cls + '">' + label + '</b></div>'; });
    list("confluenceEvidence", conf.evidence, e => { const cls = e.passed ? "pass" : "fail"; const label = e.passed ? "PASS" : "WAIT"; return '<div class="evidence-row"><span>' + esc(e.layer) + '</span><strong>' + esc(e.condition) + '</strong><b class="' + cls + '">' + label + '</b></div>'; });
    set("gateState",gate.ready?"EXECUTION ELIGIBLE":"BLOCKED"); set("gateReason",gate.ready?"All configured gates passed.":"One or more execution gates are not confirmed.");
    const gateRows=[["Market data",gate.data_fresh],["History",gate.sufficient_history],["AI",gate.ai_ready],["Broker contracts",gate.broker_contracts_confirmed],["Account scope",gate.account_scope_confirmed],["Account ready",gate.account_ready],["Risk",gate.risk_ready],["Live quote",gate.live_quote_confirmed&&gate.live_quote_fresh]];
    list("gateList", gateRows, e => { const cls = e[1] ? "pass" : "fail"; const label = e[1] ? "PASS" : "BLOCKED"; return '<div class="gate-row"><span>' + esc(e[0]) + '</span><b class="' + cls + '">' + label + '</b></div>'; });
    list("gateList", gateRows, e => { const cls = e[1] ? "pass" : "fail"; const label = e[1] ? "PASS" : "BLOCKED"; return '<div class="gate-row"><span>' + esc(e[0]) + '</span><b class="' + cls + '">' + label + '</b></div>'; });
    set("support",num(d.levels?.support));set("resistance",num(d.levels?.resistance));set("range",num(d.levels?.range));set("change",d.change_pct!=null?num(d.change_pct,2)+"%":"—");
    set("sma20",num(d.indicators?.sma20));set("sma50",num(d.indicators?.sma50));set("sma200",num(d.indicators?.sma200));set("ema",num(d.indicators?.ema9)+" / "+num(d.indicators?.ema21));set("rsi",num(d.indicators?.rsi14,2));set("atr",num(d.indicators?.atr14));set("macd",num(d.indicators?.macd?.histogram));set("bb",d.indicators?.bollinger?.width!=null?num(d.indicators.bollinger.width,2)+"%":"—");
    const fs=d.factors||[]; list("factorList",fs,x=>'<span class="tag">'+esc(x)+"</span>","No additional technical factors.");
    list("events",d.events,x=>'<div class="evidence-row"><span>'+esc(x.type)+"</span><strong>"+num(x.price)+"</strong></div>");
    list("sweeps",d.liquidity_sweeps,x=>'<div class="evidence-row"><span>'+esc(x.type)+"</span><strong>"+num(x.level)+"</strong></div>");
    list("fvgs",d.fair_value_gaps,x=>'<div class="evidence-row"><span>'+esc(x.type)+" FVG</span><strong>"+num(x.low)+"–"+num(x.high)+"</strong></div>");
    list("zones",d.supply_demand,x=>'<div class="evidence-row"><span>'+esc(x.type)+"</span><strong>"+num(x.low)+"–"+num(x.high)+"</strong></div>");
    list("patterns",d.candlestick_patterns,x=>'<div class="evidence-row"><span>'+esc(x.type)+"</span><strong>"+esc(x.bias)+"</strong></div>");
    set("account",acct.account_id||"NO ACTIVE ACCOUNT");set("accountType",acct.account_type||"—");set("currency",acct.currency||"—");set("balance",money(acct.balance,acct.currency));set("riskBudget",money(acct.risk_budget,acct.currency));set("stake",money(acct.recommended_stake,acct.currency));
    set("provenanceMarket",d.data_provenance?.broker||"—");set("provenanceCandles",d.data_provenance?.candle_source||"—");set("provenanceAnalysis","AlgoBot technical + AI pipeline");set("provenanceExecution","Broker only");
    drawChart(d.last_candles||[]);
  }

  async function load(){
    const symbol=$("symbol").value, tf=$("timeframe").value, limit=$("limit").value;
    if(!symbol)return;
    $("loadState").textContent="Loading fresh broker data…";
    try{
      const d=await request("/analysis/data/?symbol="+encodeURIComponent(symbol)+"&timeframe="+encodeURIComponent(tf)+"&limit="+limit+"&refresh=1");
      if(d.status==="error")throw new Error(d.message||"Analysis unavailable");
      render(d);$("loadState").textContent="Updated "+new Date().toLocaleTimeString();
    }catch(e){
      $("loadState").textContent=e?.message||"Analysis unavailable";setHealth(false,"UNAVAILABLE");
      $("researchState").textContent="UNAVAILABLE";$("brokerState").textContent="BROKER UNAVAILABLE";
    }
  }
  async function markets(){
    try{const d=await request("/analysis/markets/");A.markets=d.markets||[];const s=$("symbol");s.innerHTML=A.markets.map(m=>'<option value="'+esc(m.symbol)+'">'+esc(m.symbol)+" · "+esc(m.display_name||m.symbol)+"</option>").join(""); if(!s.value&&A.markets[0])s.value=A.markets[0].symbol;await load()}catch(e){$("loadState").textContent=e.message||"Markets unavailable"}}
  async function prepare(){
    if(!A.data)return;
    $("prepareState").textContent="Revalidation is performed on the selected Analysis data. Open Terminal only after review.";
    if(A.data.execution_gate?.ready){window.location.href="/trading/?symbol="+encodeURIComponent(A.data.symbol)+"&timeframe="+encodeURIComponent(A.data.timeframe)+"&direction="+encodeURIComponent(A.data.trade_spec?.direction||"");return}
    $("prepareState").textContent="BLOCKED: "+(A.data.execution_gate?.reason||"Execution gates are not confirmed.");
  }
  function boot(){
    ["symbol","timeframe","limit"].forEach(id=>$(id)?.addEventListener("change",load));
    $("refresh")?.addEventListener("click",load);$("prepare")?.addEventListener("click",prepare);
    $("auto")?.addEventListener("change",()=>{clearInterval(A.timer);if($("auto").checked)A.timer=setInterval(load,5000)});
    window.addEventListener("resize",()=>A.data&&drawChart(A.data.last_candles||[]));markets();
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot,{once:true});else boot();
})();