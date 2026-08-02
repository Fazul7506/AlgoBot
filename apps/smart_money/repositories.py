class SmartMoneyRepository:
    def __init__(self, model): self.model=model
    def latest(self, symbol=None, timeframe=None):
        qs=self.model.objects.all()
        if symbol: qs=qs.filter(symbol=symbol)
        if timeframe and hasattr(self.model,'timeframe'): qs=qs.filter(timeframe=timeframe)
        return qs.first()
    def upsert(self, **kwargs): return self.model.objects.create(**kwargs)
