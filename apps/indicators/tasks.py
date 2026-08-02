import importlib
def _celery_app():
    try: return getattr(importlib.import_module('deriv_platform.celery'),'app',None)
    except Exception: return None
def _task(fn):
    app=_celery_app(); return app.task(fn) if app else fn
@_task
def recalculate_indicators(symbol,timeframe,candles):
    from .services import IndicatorService; return IndicatorService().calculate_indicators(symbol,timeframe,candles)
@_task
def scan_patterns(symbol,timeframe,candles):
    from apps.analysis.patterns import PatternRecognitionService; return PatternRecognitionService().detect(symbol,timeframe,candles)
@_task
def update_trends(symbol,timeframe,candles):
    from apps.analysis.trend import TrendAnalysisService; return TrendAnalysisService().analyze(symbol,timeframe,candles)
@_task
def refresh_indicator_cache(): return True
@_task
def generate_historical_analysis(symbol,timeframe,candles):
    from apps.analysis.services import AnalysisService; return AnalysisService().analyze(symbol,timeframe,candles)
