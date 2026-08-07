# Broker Interface

Every broker adapter implements `apps.brokers.adapters.base.BrokerAdapter`.

Required contract: `connect`, `disconnect`, `authenticate`, `refresh_token`, `get_accounts`, `get_balance`, `get_positions`, `get_orders`, `get_open_orders`, `get_trade_history`, `get_market_data`, `subscribe_ticks`, `place_order`, `modify_order`, `cancel_order`, `close_position`, `stream_positions`, `stream_orders`, `stream_prices`, `health_check`, and `ping`.

Adapters may expose broker-specific helper methods internally, but only the standard contract may be consumed by the Trading Core.
