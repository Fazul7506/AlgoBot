class PatternRecognitionService:
    PATTERNS=['Double Top','Double Bottom','Triple Top','Triple Bottom','Head & Shoulders','Inverse Head & Shoulders','Triangle','Ascending Triangle','Descending Triangle','Symmetrical Triangle','Rectangle','Channel','Flag','Pennant','Cup & Handle','Wedge']
    def detect(self,symbol,timeframe,candles):
        closes=[float(c.get('close',c)) for c in candles]
        if len(closes)<10: return {'symbol':symbol,'timeframe':timeframe,'patterns':[]}
        direction='bullish' if closes[-1]>closes[0] else 'bearish'
        pattern='Ascending Triangle' if direction=='bullish' else 'Descending Triangle'
        return {'symbol':symbol,'timeframe':timeframe,'patterns':[{'pattern':pattern,'confidence':65,'direction':direction}]}
