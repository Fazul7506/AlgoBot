from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
try:
    from django.utils import timezone
except ModuleNotFoundError:
    from datetime import datetime, timezone as _tz
    class timezone:
        @staticmethod
        def now():
            return datetime.now(_tz.utc)
from .validators import validate_candles, clamp_score

@dataclass(frozen=True)
class Signal: type:str; direction:str='neutral'; strength:float=0; price:float|None=None; meta:dict|None=None

def _f(c,k): return float(c[k])
def swings(candles):
    highs=[]; lows=[]
    for i in range(1,len(candles)-1):
        if _f(candles[i],'high')>_f(candles[i-1],'high') and _f(candles[i],'high')>_f(candles[i+1],'high'): highs.append((i,_f(candles[i],'high')))
        if _f(candles[i],'low')<_f(candles[i-1],'low') and _f(candles[i],'low')<_f(candles[i+1],'low'): lows.append((i,_f(candles[i],'low')))
    return highs,lows
class MarketStructureService:
    def analyze(self,candles):
        validate_candles(candles); hs,ls=swings(candles); first,last=candles[0],candles[-1]
        direction='sideways'
        if _f(last,'close')>_f(first,'close') and (len(hs)<2 or hs[-1][1]>=hs[0][1]): direction='bullish'
        elif _f(last,'close')<_f(first,'close') and (len(ls)<2 or ls[-1][1]<=ls[0][1]): direction='bearish'
        rng=max(_f(x,'high')-_f(x,'low') for x in candles); net=abs(_f(last,'close')-_f(first,'open'))
        phase='expansion' if net>rng else 'consolidation'
        return {'trend':direction,'phase':phase,'structure_strength':clamp_score((net/(rng or 1))*60+20),'confidence':clamp_score(50+len(hs)+len(ls)),'swings':{'highs':hs,'lows':ls}}
class BOSService:
    def detect(self,candles):
        validate_candles(candles); hs,ls=swings(candles); close=_f(candles[-1],'close'); out=[]
        if hs and close>hs[-1][1]: out.append(Signal('bos','bullish',80,hs[-1][1],{'scope':'external' if len(hs)>2 else 'internal'}))
        if ls and close<ls[-1][1]: out.append(Signal('bos','bearish',80,ls[-1][1],{'scope':'external' if len(ls)>2 else 'internal'}))
        return out
class CHoCHService:
    def detect(self,candles):
        ms=MarketStructureService().analyze(candles[:-1]); bos=BOSService().detect(candles); return [Signal('choch',s.direction,s.strength,s.price,{'major':ms['trend']!=s.direction}) for s in bos if ms['trend']!='sideways' and ms['trend']!=s.direction]
class MSSService:
    def detect(self,candles):
        choch=CHoCHService().detect(candles); return [Signal('mss',s.direction,clamp_score(s.strength+10),s.price,{'quality':'strong' if s.strength>=75 else 'weak'}) for s in choch]
class OrderBlockService:
    def detect(self,candles):
        validate_candles(candles); blocks=[]
        for i in range(1,len(candles)-1):
            cur,nxt=candles[i],candles[i+1]; impulse=abs(_f(nxt,'close')-_f(nxt,'open'))
            avg=sum(abs(_f(c,'close')-_f(c,'open')) for c in candles[max(0,i-5):i+1])/min(i+1,6)
            if impulse>avg*1.5:
                d='bullish' if _f(nxt,'close')>_f(nxt,'open') else 'bearish'; blocks.append({'type':f'{d}_institutional','bullish':d=='bullish','bearish':d=='bearish','high':cur['high'],'low':cur['low'],'strength':clamp_score(50+impulse/(avg or 1)*10),'volume':cur.get('volume',0),'fresh':True})
        return blocks[-10:]
class FairValueGapService:
    def detect(self,candles):
        validate_candles(candles); gaps=[]
        for i in range(2,len(candles)):
            a,c=candles[i-2],candles[i]
            if _f(c,'low')>_f(a,'high'): gaps.append({'bullish':True,'bearish':False,'low':a['high'],'high':c['low'],'filled':False,'fill_percentage':0,'strength':70})
            if _f(c,'high')<_f(a,'low'): gaps.append({'bullish':False,'bearish':True,'low':c['high'],'high':a['low'],'filled':False,'fill_percentage':0,'strength':70})
        return gaps
class LiquidityService:
    def detect(self,candles,tolerance=.001):
        hs,ls=swings(candles); zones=[]
        for points,kind in ((hs,'buy_side'),(ls,'sell_side')):
            for i,p in points:
                if sum(abs(p-q)/(p or 1)<=tolerance for _,q in points)>=2: zones.append({'type':kind,'equal_high':kind=='buy_side','equal_low':kind=='sell_side','internal':i<len(candles)/2,'external':i>=len(candles)/2,'strength':75,'price':p})
        return zones
class LiquiditySweepService:
    def detect(self,candles):
        hs,ls=swings(candles[:-1]); last=candles[-1]; out=[]
        if hs and _f(last,'high')>hs[-1][1] and _f(last,'close')<hs[-1][1]: out.append(Signal('liquidity_sweep','buy_side',85,hs[-1][1],{'reversal':True}))
        if ls and _f(last,'low')<ls[-1][1] and _f(last,'close')>ls[-1][1]: out.append(Signal('liquidity_sweep','sell_side',85,ls[-1][1],{'reversal':True}))
        return out
class PremiumDiscountService:
    def calculate(self,candles):
        hi=max(_f(c,'high') for c in candles); lo=min(_f(c,'low') for c in candles); eq=(hi+lo)/2; return {'high':hi,'low':lo,'equilibrium':eq,'premium':(hi+eq)/2,'discount':(lo+eq)/2,'ote':lo+(hi-lo)*.705}
class SessionService:
    def current(self,now=None):
        from .constants import SESSIONS; now=now or timezone.now(); h=now.hour; return [{'session':s,'status':'open' if (a<=h<b if a<b else h>=a or h<b) else 'closed'} for s,(a,b) in SESSIONS.items()]
class KillZoneService(SessionService):
    def current(self,now=None):
        from .constants import KILLZONES; now=now or timezone.now(); h=now.hour; return [{'killzone':s,'status':'open' if a<=h<b else 'closed'} for s,(a,b) in KILLZONES.items()]
class InstitutionalBiasService:
    def calculate(self,candles):
        ms=MarketStructureService().analyze(candles); score=ms['structure_strength']; bias='neutral'
        if ms['trend']=='bullish': bias='strong_bullish' if score>75 else 'bullish'
        if ms['trend']=='bearish': bias='strong_bearish' if score>75 else 'bearish'
        return {'bias':bias,'confidence':clamp_score(score),'reason':f"{ms['trend']} {ms['phase']} with {score:.1f}% structure strength"}
class NarrativeService:
    def generate(self,candles):
        ms=MarketStructureService().analyze(candles); sweeps=LiquiditySweepService().detect(candles); phase='manipulation' if sweeps else ms['phase']; return {'narrative':phase,'explanation':{'structure':ms,'liquidity_sweeps':[s.__dict__ for s in sweeps]}}
class ConfluenceEngine:
    def score(self,candles):
        ms=MarketStructureService().analyze(candles); parts=[ms['structure_strength'], len(BOSService().detect(candles))*15, len(FairValueGapService().detect(candles))*5, len(LiquiditySweepService().detect(candles))*20]
        score=clamp_score(sum(parts)); label='weak' if score<40 else 'moderate' if score<60 else 'strong' if score<75 else 'very_strong' if score<90 else 'institutional_grade'; return {'score':score,'confidence':label,'components':parts}
class SmartMoneyEngine:
    def analyze(self,symbol,timeframe,candles):
        return {'symbol':symbol,'timeframe':timeframe,'market_structure':MarketStructureService().analyze(candles),'bos':[s.__dict__ for s in BOSService().detect(candles)],'choch':[s.__dict__ for s in CHoCHService().detect(candles)],'mss':[s.__dict__ for s in MSSService().detect(candles)],'order_blocks':OrderBlockService().detect(candles),'fvg':FairValueGapService().detect(candles),'liquidity':LiquidityService().detect(candles),'liquidity_sweeps':[s.__dict__ for s in LiquiditySweepService().detect(candles)],'premium_discount':PremiumDiscountService().calculate(candles),'institutional_bias':InstitutionalBiasService().calculate(candles),'narrative':NarrativeService().generate(candles),'confluence':ConfluenceEngine().score(candles)}
BreakerBlockService=MitigationBlockService=InverseFVGService=ImbalanceService=EqualHighLowService=SMTDivergenceService=OrderBlockService
EquilibriumService=PremiumDiscountService
