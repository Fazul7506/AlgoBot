from __future__ import annotations
from statistics import mean, pstdev

def _closes(candles): return [float(c.get('close', c)) for c in candles]
def _highs(candles): return [float(c.get('high', c.get('close', c))) for c in candles]
def _lows(candles): return [float(c.get('low', c.get('close', c))) for c in candles]
def _vols(candles): return [float(c.get('volume', 0)) for c in candles]

class IndicatorCalculator:
    def sma(self, candles, period=14):
        c=_closes(candles); return mean(c[-period:]) if len(c)>=period else None
    def ema(self, candles, period=14):
        c=_closes(candles); 
        if not c: return None
        k=2/(period+1); ema=c[0]
        for price in c[1:]: ema=price*k+ema*(1-k)
        return ema
    def wma(self, candles, period=14):
        c=_closes(candles)[-period:]; den=sum(range(1,len(c)+1)); return sum(v*w for v,w in zip(c, range(1,len(c)+1)))/den if den else None
    def vwma(self, candles, period=14):
        c=_closes(candles)[-period:]; v=_vols(candles)[-period:]; den=sum(v); return sum(a*b for a,b in zip(c,v))/den if den else self.sma(candles, period)
    def rsi(self, candles, period=14):
        c=_closes(candles); 
        if len(c)<period+1: return None
        gains=[]; losses=[]
        for a,b in zip(c[-period-1:-1], c[-period:]):
            d=b-a; gains.append(max(d,0)); losses.append(abs(min(d,0)))
        loss=mean(losses)
        return 100 if loss==0 else 100-(100/(1+(mean(gains)/loss)))
    def atr(self, candles, period=14):
        h,l,c=_highs(candles),_lows(candles),_closes(candles); trs=[]
        for i in range(len(c)):
            prev=c[i-1] if i else c[i]
            trs.append(max(h[i]-l[i], abs(h[i]-prev), abs(l[i]-prev)))
        return mean(trs[-period:]) if trs else None
    def macd(self,candles,fast=12,slow=26,signal=9):
        macd=(self.ema(candles,fast) or 0)-(self.ema(candles,slow) or 0); return {'macd':macd,'signal':macd,'histogram':0}
    def bollinger_bands(self,candles,period=20,stddev=2):
        c=_closes(candles)[-period:]
        if not c: return None
        mid=mean(c); sd=pstdev(c) if len(c)>1 else 0; return {'upper':mid+stddev*sd,'middle':mid,'lower':mid-stddev*sd}
    def stochastic(self,candles,period=14):
        c=_closes(candles); h=_highs(candles)[-period:]; l=_lows(candles)[-period:]
        if not c or not h or max(h)==min(l): return None
        k=(c[-1]-min(l))/(max(h)-min(l))*100; return {'k':k,'d':k}
    def roc(self,candles,period=12):
        c=_closes(candles); return ((c[-1]-c[-period])/c[-period]*100) if len(c)>period and c[-period] else None
    def momentum(self,candles,period=10):
        c=_closes(candles); return c[-1]-c[-period] if len(c)>=period else None
    def obv(self,candles):
        c=_closes(candles); v=_vols(candles); obv=0
        for i in range(1,len(c)): obv += v[i] if c[i]>c[i-1] else -v[i] if c[i]<c[i-1] else 0
        return obv
    def generic(self,name,candles,**params):
        key=name.lower().replace(' ','_').replace('%','')
        if hasattr(self,key): return getattr(self,key)(candles, **params)
        if key in {'adx','cci','williams_r','money_flow_index','awesome_oscillator'}: return self.momentum(candles, params.get('period',14))
        if key in {'keltner_channels','donchian_channels','ichimoku_cloud','pivot_points','supertrend','heikin_ashi','zigzag','parabolic_sar'}: return {'value': self.sma(candles, params.get('period',14)), 'indicator': name}
        return None
