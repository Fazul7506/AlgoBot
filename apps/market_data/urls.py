from django.urls import path
from . import api, views, scanner_api, data_center_api, intelligence_api
from . import broker_native

app_name = "market_data"
urlpatterns = [
    path("markets/", api.markets, name="markets"),
    path("markets/symbols/", api.symbols, name="symbols"),
    path("markets/symbols/sync/", api.sync_symbols, name="sync_symbols"),
    path("markets/symbol/<str:symbol>/", api.symbol_detail, name="symbol_detail_api"),
    path("market/catalogue/", broker_native.catalogue, name="broker_catalogue"),
    path("market/broker-catalogue/", broker_native.catalogue, name="broker_native_catalogue"),
    path("market/broker-capabilities/", broker_native.capabilities, name="broker_capabilities"),
    path("market/scanner/", scanner_api.scanner, name="scanner"),
    path("market/intelligence/", intelligence_api.market_intelligence, name="market_intelligence"),
    path("market/signals/lifecycle/", intelligence_api.signal_lifecycle, name="signal_lifecycle"),
    path("ticks/latest/", api.latest_tick, name="latest_tick"),
    path("ticks/history/", api.tick_history, name="tick_history_api"),
    path("ticks/broker/", api.broker_tick, name="broker_tick"),
    path("chart/capabilities/", api.broker_chart_capabilities, name="broker_chart_capabilities"),
    path("chart/history/", api.broker_chart_history, name="broker_chart_history"),
    path("market/ticks/latest/", api.latest_tick, name="market_latest_tick"),
    path("market/ticks/history/", api.tick_history, name="market_tick_history"),
    path("market/chart/capabilities/", api.broker_chart_capabilities, name="market_chart_capabilities"),
    path("market/chart/history/", api.broker_chart_history, name="market_chart_history"),
    path("market/ticks/broker/", api.broker_tick, name="market_broker_tick"),
    path("candles/", api.candles, name="candles_api"),
    path("candles/history/", api.candle_history, name="candle_history_api"),
    path("market/statistics/", api.statistics, name="statistics_api"),
    path("market/snapshot/", api.snapshot, name="snapshot_api"),
    path("data-center/quality/", data_center_api.quality, name="data_center_quality"),
    path("market-data/", views.dashboard, name="dashboard"),
]