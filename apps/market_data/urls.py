from django.urls import path
from . import api, views

app_name = "market_data"
urlpatterns = [
    path("markets/", api.markets, name="markets"),
    path("markets/symbols/", api.symbols, name="symbols"),
    path("markets/symbols/sync/", api.sync_symbols, name="sync_symbols"),
    path("markets/symbol/<str:symbol>/", api.symbol_detail, name="symbol_detail_api"),
    path("ticks/latest/", api.latest_tick, name="latest_tick"),
    path("ticks/history/", api.tick_history, name="tick_history_api"),
    path("ticks/broker/", api.broker_tick, name="broker_tick"),
    path("candles/", api.candles, name="candles_api"),
    path("candles/history/", api.candle_history, name="candle_history_api"),
    path("market/statistics/", api.statistics, name="statistics_api"),
    path("market/snapshot/", api.snapshot, name="snapshot_api"),
    path("market-data/", views.dashboard, name="dashboard"),
]
