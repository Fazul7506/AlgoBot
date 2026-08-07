# Database

Institutional trading records include `TradeExecution`, `TradeStateTransition`, `PortfolioSnapshot`, `StrategyPerformance`, `RiskEvent`, `ConnectionLog`, `PredictionHistory`, `UserPreferences`, and `MarketCandle`. Models use explicit indexes and uniqueness constraints for idempotent trade and candle ingestion.
