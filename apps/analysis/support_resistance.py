class SupportResistanceService:
    def detect(self,symbol,timeframe,candles,window=3):
        highs=[float(c.get('high',c.get('close',c))) for c in candles]; lows=[float(c.get('low',c.get('close',c))) for c in candles]
        levels=[]
        for i in range(window, max(window,len(highs)-window)):
            if highs[i]==max(highs[i-window:i+window+1]): levels.append({'level':highs[i],'type':'resistance','touches':1,'strength':60})
            if lows[i]==min(lows[i-window:i+window+1]): levels.append({'level':lows[i],'type':'support','touches':1,'strength':60})
        if highs and lows: levels += [{'level':max(highs),'type':'breakout','touches':1,'strength':80},{'level':min(lows),'type':'retest','touches':1,'strength':80}]
        return {'symbol':symbol,'timeframe':timeframe,'levels':levels[-20:]}
