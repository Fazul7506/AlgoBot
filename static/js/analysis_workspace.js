(() => {
  "use strict";
  if (window.__algoBotAnalysisWorkspace) return;
  window.__algoBotAnalysisWorkspace = true;
  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? "—").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const num = (v,d=5) => v==null || v==="" || !Number.isFinite(Number(v)) ? "—" : Number(v).toLocaleString(undefined,{maximumFractionDigits:d});
  const pct = v => v==null || v==="" || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(1)+"%";
  const money = (v,c) => v==null || v==="" || !Number.isFinite(Number(v)) ? "—" : (c ? c+" " : "")+Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
  const state = v => String(v ?? "UNAVAILABLE").replaceAll("_"," ");
  const tone = v => ["BUY","BULLISH","STRONG BULLISH"].includes(String(v||"").toUpperCase()) ? "positive" : ["SELL","BEARISH","STRONG BEARISH"].includes(String(v||"").toUpperCase()) ? "negative" : "neutral";
  const A = {markets:[],data:null,contract:null,timer:null,loadGeneration:0};

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

  function emaSeries(values, period){
    const out=Array(values.length).fill(null); if(values.length<period)return out;
    const k=2/(period+1); let current=values.slice(0,period).reduce((a,b)=>a+b,0)/period; out[period-1]=current;
    for(let i=period;i<values.length;i++){current=values[i]*k+current*(1-k);out[i]=current}
    return out;
  }
  function drawLinePanel(canvasId,emptyId,series,opts={}){
    const canvas=$(canvasId), empty=$(emptyId); if(!canvas)return;
    const valid=series.filter(s=>Array.isArray(s.values)&&s.values.some(Number.isFinite));
    if(!valid.length){canvas.hidden=true;if(empty)empty.hidden=false;return}
    canvas.hidden=false;if(empty)empty.hidden=true;
    const box=canvas.getBoundingClientRect(),q=window.devicePixelRatio||1,w=Math.max(240,box.width),h=Math.max(90,box.height);
    canvas.width=Math.round(w*q);canvas.height=Math.round(h*q);const ctx=canvas.getContext("2d");ctx.setTransform(q,0,0,q,0,0);ctx.clearRect(0,0,w,h);
    const pad={l:8,r:8,t:8,b:8},n=Math.max(...valid.map(s=>s.values.length));
    let lo=opts.min??Math.min(...valid.flatMap(s=>s.values.filter(Number.isFinite))),hi=opts.max??Math.max(...valid.flatMap(s=>s.values.filter(Number.isFinite)));
    if(opts.min==null){const span=hi-lo||1;lo-=span*.12;hi+=span*.12}
    if(hi===lo)hi=lo+1;
    const px=i=>pad.l+i/Math.max(1,n-1)*(w-pad.l-pad.r),py=v=>h-pad.b-(v-lo)/(hi-lo)*(h-pad.t-pad.b);
    ctx.lineWidth=1;ctx.strokeStyle="rgba(148,177,211,.18)";
    for(let i=1;i<4;i++){const y=pad.t+(h-pad.t-pad.b)*i/4;ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(w-pad.r,y);ctx.stroke()}
    (opts.levels||[]).forEach(level=>{ctx.save();ctx.setLineDash([4,4]);ctx.strokeStyle="rgba(167,186,215,.55)";ctx.beginPath();ctx.moveTo(pad.l,py(level));ctx.lineTo(w-pad.r,py(level));ctx.stroke();ctx.restore()});
    valid.forEach(s=>{ctx.beginPath();ctx.strokeStyle=s.color;ctx.lineWidth=1.6;let started=false;s.values.forEach((v,i)=>{if(!Number.isFinite(v)){started=false;return}if(!started){ctx.moveTo(px(i),py(v));started=true}else ctx.lineTo(px(i),py(v))});ctx.stroke()});
    if(opts.zero){ctx.strokeStyle="rgba(167,186,215,.55)";ctx.beginPath();ctx.moveTo(pad.l,py(0));ctx.lineTo(w-pad.r,py(0));ctx.stroke()}
  }
  function drawIndicators(candles){
    const closes=(candles||[]).map(c=>Number(c.close)).filter(Number.isFinite);
    if(closes.length<2){drawLinePanel("macdChart","macdEmpty",[]);drawLinePanel("rsiChart","rsiEmpty",[]);return}
    const fast=emaSeries(closes,12),slow=emaSeries(closes,26);
    const macd=closes.map((_,i)=>fast[i]!=null&&slow[i]!=null?fast[i]-slow[i]:null);
    const macdValues=macd.filter(Number.isFinite),signalCompact=emaSeries(macdValues,9);
    const signal=Array(macd.length).fill(null);let si=0;macd.forEach((v,i)=>{if(Number.isFinite(v)){signal[i]=signalCompact[si++]}});
    drawLinePanel("macdChart","macdEmpty",[
      {values:macd,color:"#a78bfa"},{values:signal,color:"#f6ad45"}
    ],{zero:true});
    const rsi=Array(closes.length).fill(null);
    if(closes.length>=15){let gains=0,losses=0;for(let i=1;i<=14;i++){const d=closes[i]-closes[i-1];if(d>=0)gains+=d;else losses-=d}
      let avgGain=gains/14,avgLoss=losses/14;rsi[14]=avgLoss===0?100:100-100/(1+avgGain/avgLoss);
      for(let i=15;i<closes.length;i++){const d=closes[i]-closes[i-1];avgGain=(avgGain*13+Math.max(d,0))/14;avgLoss=(avgLoss*13+Math.max(-d,0))/14;rsi[i]=avgLoss===0?100:100-100/(1+avgGain/avgLoss)}
    }
    drawLinePanel("rsiChart","rsiEmpty",[{values:rsi,color:"#a78bfa"}],{min:0,max:100,levels:[30,50,70]});
  }

  function render(d){
    A.data=d;
    const gate=d.execution_gate||{}, ai=d.ai||{}, layers=d.analysis_layers||{}, conf=d.confluence||{}, acct=d.account_context||{};
    set("aResearchState",state(d.research_state)); set("aBrokerState",state(d.broker_state)); set("aSymbol",d.symbol); set("aTf",String(d.timeframe||"M1").toUpperCase()); set("aPrice",num(d.price)); set("aSignal",d.signal==null?"UNAVAILABLE":d.signal); $("aSignal").className="value "+tone(d.signal); set("aTechnical",d.score!=null?num(d.score,1)+"/100":"Technical score —"); set("aFresh",d.data_provenance?.fresh?"FRESH DATA":"DATA UNVERIFIED"); set("liveQuote",num(d.live_quote?.price)); set("liveQuoteAge",d.live_quote?.age_seconds!=null?"Live quote age "+d.live_quote.age_seconds+"s":"Live quote freshness unavailable"); set("liveQuoteSource",d.live_quote?.source||"Deriv live quote");
    set("aTechnical",d.score!=null?num(d.score,1)+"/100":"—"); set("aConfidence",pct(d.confidence)); set("aRegime",d.volatility_regime);
    const sentiment=d.sentiment&&typeof d.sentiment==="object"?d.sentiment:null;
    const sentimentLabel=sentiment?.label||sentiment?.sentiment||sentiment?.classification;
    set("sentimentState",sentimentLabel?state(sentimentLabel):"Unavailable");
    set("sentimentScore",sentiment?.score!=null?("Score "+num(sentiment.score,1)):"No verified score");
    set("sentimentSummary",sentiment?.summary||sentiment?.source||"No sentiment feed supplied"); set("aFresh",d.data_provenance?.fresh?"FRESH":"STALE");
    const quoteFresh=Boolean(d.data_provenance?.fresh && d.live_quote?.fresh); setHealth(quoteFresh,quoteFresh?"DERIV LIVE":"DATA NOT FRESH"); const heroState=$("heroFeedState"); if(heroState)heroState.textContent=quoteFresh?"Live market feed connected":"Market data needs verification"; const pulse=document.querySelector(".status-pulse"); if(pulse)pulse.classList.toggle("is-live",quoteFresh);
    set("marketState",state(layers.market_data?.state)); set("marketSource",layers.market_data?.source||d.data_provenance?.broker); set("marketAge",d.data_provenance?.age_seconds!=null?d.data_provenance.age_seconds+"s":"—"); set("candleCount",d.candles??d.last_candles?.length);
    set("trendState",layers.technical?.structure||d.structure); set("trendScore",layers.technical?.score!=null?num(layers.technical.score,1)+"/100":"—"); set("momentumState",d.indicators?.rsi14!=null?"RSI "+num(d.indicators.rsi14,1):"—"); set("volatilityState",d.volatility_regime);
    set("strategyState",state(layers.strategy?.state)); set("strategyDirection",layers.strategy?.direction||"WAIT"); set("strategyEvidence",(layers.strategy?.evidence||[]).join(" · ")||"No persisted strategy evidence");
    set("aiState",state(layers.ai?.state)); set("aiDecision",layers.ai?.decision||"UNAVAILABLE"); set("aiConfidence",pct(layers.ai?.confidence)); set("aiModels",layers.ai?.models_used?String(layers.ai.models_used):"0"); set("aiAgreement",layers.ai?.agreement!=null?pct(Number(layers.ai.agreement)*100):"—");
    set("confluenceState",state(conf.state)); set("confluenceDirection",conf.direction||"WAIT"); set("confluenceScore",conf.score!=null?num(conf.score,1)+"/100":"—");
    list("confluenceEvidence", conf.evidence, e => { const cls = e.passed ? "pass" : "fail"; const label = e.passed ? "PASS" : "WAIT"; return '<div class="evidence-row"><span>' + esc(e.layer) + '</span><strong>' + esc(e.condition) + '</strong><b class="' + cls + '">' + label + '</b></div>'; });
    set("gateState",gate.ready?"EXECUTION ELIGIBLE":"BLOCKED"); set("gateReason",gate.reason|| (gate.ready?"All configured gates passed.":"One or more execution gates are not confirmed.")); set("validationState",state(d.signal_validation?.state)); set("validationDirection",d.signal_validation?.signal||"WAIT"); set("validationExpiry",d.signal_validation?.expires_after_seconds!=null?d.signal_validation.expires_after_seconds+" seconds":"—"); set("noLookAhead",d.signal_validation?.no_look_ahead===true?"CONFIRMED":"UNCONFIRMED");
    const gateRows=[["Market data",gate.data_fresh],["History",gate.sufficient_history],["AI",gate.ai_ready],["Broker contracts",gate.broker_contracts_confirmed],["Account scope",gate.account_scope_confirmed],["Account ready",gate.account_ready],["Risk",gate.risk_ready],["Live quote",gate.live_quote_confirmed&&gate.live_quote_fresh]];
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
    drawChart(d.last_candles||[]); drawIndicators(d.last_candles||[]);
  }

  async function load(options={}){
    const generation=++A.loadGeneration;
    const symbol=$("symbol").value, tf=$("timeframe").value, limit=$("limit").value;
    if(!symbol){$("loadState").textContent="No active market is available.";return}
    $("loadState").textContent="Loading fresh broker data…";
    try{
      const refreshAccount=options.refreshAccount===true;
      const d=await request("/analysis/data/?symbol="+encodeURIComponent(symbol)+"&timeframe="+encodeURIComponent(tf)+"&limit="+limit+"&refresh=1&refresh_account="+(refreshAccount?"1":"0"));
      if(generation!==A.loadGeneration||symbol!==$("symbol").value||tf!==$("timeframe").value||limit!==$("limit").value)return;
      if(d.status==="error")throw new Error(d.message||"Analysis unavailable");
      render(d);$("loadState").textContent="Updated "+new Date().toLocaleTimeString();
    }catch(e){
      if(generation!==A.loadGeneration)return;
      A.data=null;
      $("loadState").textContent=e?.message||"Analysis unavailable";setHealth(false,"UNAVAILABLE");
      set("aResearchState","UNAVAILABLE");set("aBrokerState","UNAVAILABLE");set("aPrice","—");set("aSignal","UNAVAILABLE");set("aTechnical","Technical score —");set("aFresh","DATA UNAVAILABLE");set("liveQuote","UNAVAILABLE");set("liveQuoteAge","Live quote freshness unavailable");set("liveQuoteSource","—");set("validationState","UNAVAILABLE");set("validationDirection","WAIT");set("validationExpiry","—");set("noLookAhead","UNCONFIRMED");const heroState=$("heroFeedState");if(heroState)heroState.textContent="Market feed unavailable";const pulse=document.querySelector(".status-pulse");if(pulse)pulse.classList.remove("is-live");
      set("marketState","UNAVAILABLE");set("marketSource","—");set("marketAge","—");set("candleCount","—");
      set("liveQuote","UNAVAILABLE");set("liveQuoteAge","—");set("liveQuoteSource","—");
      set("gateState","BLOCKED");set("gateReason","Fresh analysis evidence could not be confirmed.");
      set("account","NO VERIFIED ACCOUNT CONTEXT");set("accountType","—");set("currency","—");set("balance","—");set("riskBudget","—");set("stake","—");
      drawChart([]);
    }
  }
  async function markets(){
    try{
      const d=await request("/analysis/markets/");
      A.markets=d.markets||[];
      const s=$("symbol");
      s.innerHTML=A.markets.map(m=>'<option value="'+esc(m.symbol)+'">'+esc(m.symbol)+" · "+esc(m.display_name||m.symbol)+"</option>").join("");
      if(!A.markets.length){$("loadState").textContent="No active markets are available.";setHealth(false,"UNAVAILABLE");return}
      if(!s.value&&A.markets[0])s.value=A.markets[0].symbol;
      await load({refreshAccount:true});
    }catch(e){$("loadState").textContent=e.message||"Markets unavailable"}
  }
  async function prepare(){
    if(!A.data)return;
    $("prepareState").textContent="Revalidation is performed on the selected Analysis data. Open Terminal only after review.";
    if(A.data.execution_gate?.ready){window.location.href="/trading/?symbol="+encodeURIComponent(A.data.symbol)+"&timeframe="+encodeURIComponent(A.data.timeframe)+"&direction="+encodeURIComponent(A.data.trade_spec?.direction||"");return}
    $("prepareState").textContent="BLOCKED: "+(A.data.execution_gate?.reason||"Execution gates are not confirmed.");
  }
  function boot(){
    ["symbol","timeframe","limit"].forEach(id=>$(id)?.addEventListener("change",()=>load()));
    $("refresh")?.addEventListener("click",()=>load({refreshAccount:true}));$("prepare")?.addEventListener("click",prepare);
    $("auto")?.addEventListener("change",()=>{clearInterval(A.timer);if($("auto").checked)A.timer=setInterval(()=>load({refreshAccount:false}),15000)});
    window.addEventListener("resize",()=>{if(A.data){drawChart(A.data.last_candles||[]);drawIndicators(A.data.last_candles||[])}});markets();
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot,{once:true});else boot();
})();