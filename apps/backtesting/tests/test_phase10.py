from apps.backtesting.services import BacktestingEngine, MarketEvent, MonteCarloService, ParameterOptimizationService, ReplayService, DatasetGeneratorService

def test_backtesting_engine_runs_shared_pipeline():
    engine=BacktestingEngine(); result=engine.run([MarketEvent(1,'R_100',100)])
    assert 'statistics' in result and result['mode']=='candle_close'
def test_monte_carlo_and_optimization_and_replay():
    assert MonteCarloService().run([{'profit':1},{'profit':-1}], runs=100)['runs']==100
    assert ParameterOptimizationService().optimize('grid', {'a':[1,2]})[0]['parameters']['a']==2
    assert ReplayService().play()['event']=='ReplayStarted'
def test_dataset_generator():
    assert DatasetGeneratorService().generate([MarketEvent(1,'R_100',100)], [], purpose='ai_training')
