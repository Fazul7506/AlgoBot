from .engine import StrategyEngine
class StrategyManager:
    def __init__(self): self.engine=StrategyEngine()
    def run_active(self, **kwargs): return self.engine.run(**kwargs)
