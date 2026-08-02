EVENTS=['BacktestStarted','BacktestCompleted','OptimizationStarted','OptimizationCompleted','PaperTradeExecuted','ReplayStarted','ReplayPaused','ReplayFinished','SimulationUpdated']
def broadcast(event, payload=None):
    if event not in EVENTS: raise ValueError(f'Unsupported event {event}')
    return {'event':event,'payload':payload or {}}
