import importlib, inspect, pkgutil
from .exceptions import StrategyRegistryError
REQUIRED_METHODS=['initialize','validate','analyze_market','generate_signal','calculate_confidence','calculate_stop_loss','calculate_take_profit','calculate_position_size','execute','shutdown']

class StrategyRegistry:
    def __init__(self): self._strategies={}
    def register(self, strategy_cls):
        missing=[m for m in REQUIRED_METHODS if not callable(getattr(strategy_cls,m,None))]
        if missing: raise StrategyRegistryError(f'{strategy_cls.__name__} missing {missing}')
        self._strategies[getattr(strategy_cls,'slug',strategy_cls.__name__)]=strategy_cls; return strategy_cls
    def get(self, slug): return self._strategies.get(slug)
    def all(self): return dict(self._strategies)
    def discover(self):
        from .built_in import BUILT_IN_STRATEGIES
        for cls in BUILT_IN_STRATEGIES: self.register(cls)
        self.discover_plugins(); return self
    def discover_plugins(self, package='apps.strategies.plugins'):
        module=importlib.import_module(package)
        for info in pkgutil.iter_modules(module.__path__, package+'.'):
            mod=importlib.import_module(info.name)
            for _, obj in inspect.getmembers(mod, inspect.isclass):
                if all(callable(getattr(obj,m,None)) for m in REQUIRED_METHODS): self.register(obj)
        return self
registry=StrategyRegistry().discover()
