class TrendAnalysisService:
    labels=['Strong Bearish','Bearish','Weak Bearish','Sideways','Weak Bullish','Bullish','Strong Bullish']
    def analyze(self,symbol,timeframe,candles,indicators=None):
        closes=[float(c.get('close',c)) for c in candles]
        if len(closes)<2: score=0
        else: score=(closes[-1]-closes[0])/(abs(closes[0]) or 1)*100
        momentum=(closes[-1]-closes[-5]) if len(closes)>=5 else score
        volatility=(max(closes)-min(closes))/(sum(closes)/len(closes) or 1)*100 if closes else 0
        idx=3 + (1 if score>0.2 else 0) + (1 if score>1 else 0) + (1 if score>3 else 0) - (1 if score<-0.2 else 0) - (1 if score<-1 else 0) - (1 if score<-3 else 0)
        trend=self.labels[max(0,min(6,idx))]; strength=min(100,abs(score)*10+abs(momentum)); confidence=min(100,50+strength/2)
        return {'symbol':symbol,'timeframe':timeframe,'trend':trend,'strength':strength,'confidence':confidence,'scores':{'trend':score,'momentum':momentum,'volatility':volatility,'confidence':confidence}}
