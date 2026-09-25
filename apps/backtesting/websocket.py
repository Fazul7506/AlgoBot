EVENTS=['BacktestStarted','BacktestCompleted','OptimizationStarted','OptimizationCompleted','ReplayStarted','ReplayPaused','ReplayFinished']
def broadcast(event, payload=None):
    if event not in EVENTS: raise ValueError(f'Unsupported event {event}')
    return {'event':event,'payload':payload or {}}
