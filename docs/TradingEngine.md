# Trading Engine

The institutional execution pipeline is Market Data → Indicators → Strategy Engine → Signal Validation → Risk Engine → Position Sizing → Execution Queue → Broker Adapter → Trade State Machine → Portfolio → Analytics → Dashboard. Signal validation returns structured `ValidationResult` objects; trade lifecycle transitions are persisted by `TradeStateMachine`.
