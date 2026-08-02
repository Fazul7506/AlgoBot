"""Strategy service alias for compatibility with trading.services imports."""

from trading.strategies.strategy_service import StrategyService as StrategyServiceImpl

StrategyService = StrategyServiceImpl
