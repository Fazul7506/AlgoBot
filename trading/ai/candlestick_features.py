"""Broker-independent candlestick/price-action features.

Implements quantitative features inspired by standard candlestick and price-action
concepts: candle anatomy, major single/multi-candle patterns, market structure,
support/resistance, trend direction, range/chop detection, Fibonacci location,
and top-down/confluence signals.

This module stores rules/measurements, not copied educational prose from any book.
"""
from __future__ import annotations
from typing import Iterable
import numpy as np

FEATURE_NAMES=("body_ratio","upper_wick_ratio","lower_wick_ratio","bullish_candle","doji","hammer","shooting_star","bullish_engulfing","bearish_engulfing","morning_star","evening_star","inside_bar","pin_bar_bull","pin_bar_bear","tweezer_top","tweezer_bottom","trend_score","range_score","chop_score","support_distance","resistance_distance","breakout_up","breakout_down","fib_382","fib_500","fib_618","volume_pressure","confluence_score","price_return_1","price_return_5","atr_norm","htf_trend_score","mtf_alignment")

def _safe(a,default=0.0):
    try:
        x=float(a); return x if np.isfinite(x) else default
    except (TypeError,ValueError): return default

def _candle(o,h,l,c):
    rng=max(abs(h-l),1e-12); body=abs(c-o)
    return {"range":rng,"body":body,"body_ratio":body/rng,"upper":max(0.0,h-max(o,c))/rng,"lower":max(0.0,min(o,c)-l)/rng,"bull":c>o}

def _slope_score(values):
    values=np.asarray(values,dtype=float); x=np.arange(len(values),dtype=float)
    slope=float(np.polyfit(x,values,1)[0]) if len(values)>1 else 0.0
    return float(np.tanh((slope/(np.mean(values) or 1e-12))*100.0))

def extract_candlestick_features(candles:Iterable[dict])->dict[str,float]:
    rows=list(candles)
    if len(rows)<25: raise ValueError("At least 25 OHLC candles are required")
    o=np.asarray([_safe(x.get("open")) for x in rows],dtype=float); h=np.asarray([_safe(x.get("high")) for x in rows],dtype=float); l=np.asarray([_safe(x.get("low")) for x in rows],dtype=float); c=np.asarray([_safe(x.get("close")) for x in rows],dtype=float); v=np.asarray([_safe(x.get("volume"),0.0) for x in rows],dtype=float)
    cur=_candle(o[-1],h[-1],l[-1],c[-1]); prev=_candle(o[-2],h[-2],l[-2],c[-2]); p2=_candle(o[-3],h[-3],l[-3],c[-3])
    atr=float(np.mean(np.abs(h[-14:]-l[-14:]))) or 1e-12; recent_high=float(np.max(h[-20:-1])); recent_low=float(np.min(l[-20:-1])); span=max(recent_high-recent_low,1e-12)
    trend_score=_slope_score(c[-20:]); htf_trend_score=_slope_score(c[-60:]) if len(c)>=60 else _slope_score(c); mtf_alignment=float(np.sign(trend_score)==np.sign(htf_trend_score))
    returns=np.diff(c[-21:])/np.where(c[-21:-1]==0,1,c[-21:-1]); chop_score=float(np.clip(np.std(returns)/(abs(np.mean(returns))+1e-9),0,10)/10); range_score=float(np.clip(span/(atr*20),0,1))
    doji=float(cur["body_ratio"]<=.10); hammer=float(cur["lower"]>=.55 and cur["upper"]<=.20 and cur["body_ratio"]<=.45); shooting=float(cur["upper"]>=.55 and cur["lower"]<=.20 and cur["body_ratio"]<=.45)
    bull_engulf=float((not prev["bull"]) and cur["bull"] and o[-1]<=c[-2] and c[-1]>=o[-2]); bear_engulf=float(prev["bull"] and (not cur["bull"]) and o[-1]>=c[-2] and c[-1]<=o[-2])
    morning=float((not p2["bull"]) and p2["body_ratio"]>.5 and prev["body_ratio"]<.35 and cur["bull"] and c[-1]>(o[-3]+c[-3])/2); evening=float(p2["bull"] and p2["body_ratio"]>.5 and prev["body_ratio"]<.35 and (not cur["bull"]) and c[-1]<(o[-3]+c[-3])/2)
    inside=float(h[-1]<=h[-2] and l[-1]>=l[-2]); pin_bull=float(cur["lower"]>=.60 and cur["body_ratio"]<=.40); pin_bear=float(cur["upper"]>=.60 and cur["body_ratio"]<=.40)
    tol=atr*.15; tweezer_top=float(abs(h[-1]-h[-2])<=tol and cur["bull"] and not prev["bull"]); tweezer_bottom=float(abs(l[-1]-l[-2])<=tol and not cur["bull"] and prev["bull"])
    support_distance=(c[-1]-recent_low)/span; resistance_distance=(recent_high-c[-1])/span; breakout_up=float(c[-1]>recent_high); breakout_down=float(c[-1]<recent_low); fib_pos=(c[-1]-recent_low)/span
    vol_pressure=0.0
    if np.mean(v[-10:])>0: vol_pressure=float(np.clip((v[-1]/np.mean(v[-10:]))-1,-3,3)/3)
    directional=(bull_engulf+morning+hammer+pin_bull+tweezer_bottom+breakout_up)-(bear_engulf+evening+shooting+pin_bear+tweezer_top+breakout_down)
    confluence=float(np.clip(.5+.08*directional+.12*trend_score+.08*(1-chop_score)+.08*float(mtf_alignment),0,1))
    return {"body_ratio":cur["body_ratio"],"upper_wick_ratio":cur["upper"],"lower_wick_ratio":cur["lower"],"bullish_candle":float(cur["bull"]),"doji":doji,"hammer":hammer,"shooting_star":shooting,"bullish_engulfing":bull_engulf,"bearish_engulfing":bear_engulf,"morning_star":morning,"evening_star":evening,"inside_bar":inside,"pin_bar_bull":pin_bull,"pin_bar_bear":pin_bear,"tweezer_top":tweezer_top,"tweezer_bottom":tweezer_bottom,"trend_score":trend_score,"range_score":range_score,"chop_score":chop_score,"support_distance":support_distance,"resistance_distance":resistance_distance,"breakout_up":breakout_up,"breakout_down":breakout_down,"fib_382":float(abs(fib_pos-.382)),"fib_500":float(abs(fib_pos-.500)),"fib_618":float(abs(fib_pos-.618)),"volume_pressure":vol_pressure,"confluence_score":confluence,"price_return_1":float(returns[-1]),"price_return_5":float((c[-1]/c[-6])-1),"atr_norm":float(atr/(abs(c[-1]) or 1e-12)),"htf_trend_score":htf_trend_score,"mtf_alignment":mtf_alignment}

def feature_vector(candles:Iterable[dict])->list[float]:
    f=extract_candlestick_features(candles); return [float(f[name]) for name in FEATURE_NAMES]
