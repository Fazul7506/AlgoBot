import logging
from .services import SmartMoneyEngine
logger=logging.getLogger(__name__)
def analyze_market_structure(symbol, timeframe, candles): logger.info('SMC analysis started for %s %s',symbol,timeframe); return SmartMoneyEngine().analyze(symbol,timeframe,candles)
scan_order_blocks=scan_fvg=scan_liquidity=monitor_sessions=recalculate_institutional_bias=update_confluence=generate_alerts=analyze_market_structure
