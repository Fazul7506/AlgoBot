from django.urls import path
from . import api, views

app_name = "market_data"
urlpatterns = [
    path("markets/", api.markets, name="markets"),
    path("markets/symbols/", api.symbols, name="symbols"),
    path("markets/symbols/sync/", api.sync_symbols, name="sync_symbols"),
    path("markets/symbol/<str:symbol>/", api.symbol_detail, name="symbol_detail_api"),
    path("market/catalogue/", api.broker_catalogue, name="broker_catalogue"),
    path("ticks/latest/", api.latest_tick, name="latest_tick"),
    path("ticks/history/", api.tick_history, name="tick_history_api"),
    path("ticks/broker/", api.broker_tick, name="broker_tick"),
    path("chart/capabilities/", api.broker_chart_capabilities, name="broker_chart_capabilities"),
    path("chart/history/", api.broker_chart_history, name="broker_chart_history"),
    path("market/ticks/broker/", api.broker_tick, name="market_broker_tick"),
    path("candles/", api.candles, name="candles_api"),
    path("candles/history/", api.candle_history, name="candle_history_api"),
    path("market/statistics/", api.statistics, name="statistics_api"),
    path("market/snapshot/", api.snapshot, name="snapshot_api"),
    path("market-data/", views.dashboard, name="dashboard"),
]
