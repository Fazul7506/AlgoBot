from statistics import mean, pstdev
from apps.indicators.calculator import IndicatorCalculator
class VolatilityService:
    def analyze(self,symbol,timeframe,candles,period=14):
        closes=[float(c.get('close',c)) for c in candles]
        rets=[(b-a)/(a or 1) for a,b in zip(closes[:-1],closes[1:])]
        rolling=pstdev(rets[-period:])*100 if len(rets)>1 else 0
        atr=IndicatorCalculator().atr(candles,period) or 0
        expansion=bool(rolling > (pstdev(rets)*100 if len(rets)>1 else rolling+1))
        return {'symbol':symbol,'timeframe':timeframe,'atr':atr,'historical_volatility':pstdev(rets)*100 if len(rets)>1 else 0,'rolling_volatility':rolling,'price_expansion':expansion,'compression_zone':not expansion and rolling<1}
