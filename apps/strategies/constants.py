STRATEGY_CATEGORIES = [
    'Trend Following','Mean Reversion','Momentum','Breakout','Scalping','Swing Trading','Range Trading',
    'Volatility Trading','Support & Resistance','News Trading','Smart Money Concepts','ICT Concepts',
    'Liquidity Trading','AI Hybrid Strategies',
]
SIGNAL_TYPES = ['BUY','SELL','STRONG BUY','STRONG SELL','HOLD','EXIT','REDUCE POSITION','ADD POSITION']
CONFIDENCE_LABELS = [(0,20,'Very Low'),(20,40,'Low'),(40,60,'Medium'),(60,80,'High'),(80,101,'Very High')]
LIFECYCLE_STATES = ['created','validated','loaded','initialized','running','paused','stopped','archived']
EXECUTION_STATUS = ['pending','running','completed','failed','skipped']
SCHEDULE_TYPES = ['continuous','every_tick','every_candle','every_minute','every_5_minutes','every_15_minutes','hourly','custom_cron']
CONFLICT_RESOLUTION = ['highest_confidence','weighted_voting','majority_vote','priority_strategy','ai_arbitration']
RISK_PROFILES = ['conservative','balanced','aggressive','custom']
