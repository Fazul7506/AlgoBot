# Research Data Contract

## Source of truth

`apps.market_data.models.Candle` is the canonical OHLCV source for historical research. Broker APIs are ingestion sources only. Research features must not silently fetch fresh broker history and mix it with the persisted dataset.

## Scope

This contract applies to:

- Analysis: trend, volatility, support/resistance and pattern research.
- Indicators and multi-timeframe indicator calculations.
- Strategy historical evaluation and strategy-builder research.
- Backtesting, replay and walk-forward research inputs.
- AI feature generation, training datasets and historical validation.
- Research analytics and data-quality/freshness views.

Tick-mode research may use the persisted `Tick` table. It must not replace candle-mode research with an unpersisted broker response.

## Timeframes

Use `apps.market_data.historical.normalize_timeframe()` at every research boundary. Canonical values are the keys in `apps.market_data.constants.TIMEFRAMES` (`tick`, `1s`, `5s`, `15s`, `30s`, `1m`, `2m`, `5m`, `10m`, `15m`, `30m`, `1h`, `2h`, `4h`, `8h`, `1d`). Legacy aliases such as `M1`, `M5`, `H1`, `H4` are normalized before querying the database.

## Reproducibility requirements

1. Research reads chronological rows from the database.
2. A requested symbol must resolve to an active `MarketSymbol`.
3. A requested timeframe is normalized before querying `Candle`.
4. Date-range research filters by candle `epoch` boundaries.
5. AI dataset metadata identifies `market_data.Candle` and database storage.
6. Missing persisted history is reported explicitly; it must not trigger a hidden broker-history fallback.
7. Broker historical fetching remains in market-data ingestion/backfill jobs, where results are persisted before research consumes them.

`ResearchDataService` is the shared read path for these requirements.
