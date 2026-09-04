from django.contrib import admin
from .models import Tick, Trade, BacktestResult, Candle, Signal, PerformanceSnapshot, Strategy
from .models.logging import SystemLog, TradeLog, ErrorLog
from .models.market import MarketSymbol, PriceHistory, MarketSnapshot, TickData, DataStreamSession
from .models.indicators import IndicatorValue, TechnicalSignal, IndicatorProfile, IndicatorAlert


# Keep the Django admin clearly branded and operationally focused for AlgoBot.
admin.site.site_header = "AlgoBot Administration"
admin.site.site_title = "AlgoBot Admin"
admin.site.index_title = "Trading Platform Operations"


@admin.register(Tick)
class TickAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'price', 'epoch', 'created_at']
    list_filter = ['symbol', 'created_at']
    search_fields = ['symbol']
    list_per_page = 50


@admin.register(Strategy)
class StrategyAdmin(admin.ModelAdmin):
    list_display = ['name', 'strategy_type', 'is_active', 'win_rate', 'total_pnl']
    list_filter = ['strategy_type', 'is_active']
    search_fields = ['name']
    list_per_page = 50


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ['user', 'symbol', 'contract_type', 'status', 'stake', 'profit', 'opened_at']
    list_filter = ['status', 'symbol', 'opened_at']
    search_fields = ['user__username', 'symbol']
    readonly_fields = ['opened_at', 'closed_at']
    list_per_page = 50
    date_hierarchy = 'opened_at'


@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'direction', 'confidence', 'market_regime', 'was_executed', 'created_at']
    list_filter = ['direction', 'market_regime', 'was_executed', 'created_at']
    search_fields = ['symbol']
    list_per_page = 50


@admin.register(BacktestResult)
class BacktestResultAdmin(admin.ModelAdmin):
    list_display = ['strategy', 'symbol', 'win_rate', 'sharpe_ratio', 'created_at']
    list_filter = ['strategy', 'symbol', 'created_at']
    search_fields = ['strategy']
    list_per_page = 50


@admin.register(Candle)
class CandleAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'timeframe', 'open', 'close', 'timestamp']
    list_filter = ['symbol', 'timeframe', 'timestamp']
    search_fields = ['symbol']
    list_per_page = 50


@admin.register(PerformanceSnapshot)
class PerformanceSnapshotAdmin(admin.ModelAdmin):
    list_display = ['user', 'balance', 'pnl', 'pnl_pct', 'created_at']
    list_filter = ['is_paper', 'created_at']
    search_fields = ['user__username']
    readonly_fields = ['created_at']
    list_per_page = 50


@admin.register(SystemLog)
class SystemLogAdmin(admin.ModelAdmin):
    list_display = ['level', 'module', 'message', 'created_at']
    list_filter = ['level', 'module', 'created_at']
    search_fields = ['message', 'module']
    readonly_fields = ['created_at', 'message']
    list_per_page = 50
    date_hierarchy = 'created_at'


@admin.register(TradeLog)
class TradeLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'symbol', 'strategy', 'pnl', 'created_at']
    list_filter = ['action', 'symbol', 'created_at']
    search_fields = ['user__username', 'symbol']
    readonly_fields = ['created_at']
    list_per_page = 50
    date_hierarchy = 'created_at'


@admin.register(ErrorLog)
class ErrorLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'error_type', 'severity', 'resolved', 'created_at']
    list_filter = ['severity', 'resolved', 'created_at']
    search_fields = ['user__username', 'error_type']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 50
    date_hierarchy = 'created_at'


@admin.register(MarketSymbol)
class MarketSymbolAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'display_name', 'market_type', 'is_active', 'is_tradeable', 'last_tick_time']
    list_filter = ['market_type', 'is_active', 'is_tradeable']
    search_fields = ['symbol', 'display_name']
    readonly_fields = ['created_at', 'updated_at', 'last_tick_time']
    list_per_page = 50


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'timeframe', 'open', 'high', 'low', 'close', 'candle_time']
    list_filter = ['symbol', 'timeframe', 'candle_time']
    search_fields = ['symbol__symbol']
    readonly_fields = ['created_at']
    list_per_page = 50
    date_hierarchy = 'candle_time'


@admin.register(MarketSnapshot)
class MarketSnapshotAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'last_price', 'bid_ask_spread', 'change_pct_24h', 'updated_at']
    list_filter = ['updated_at']
    search_fields = ['symbol__symbol']
    readonly_fields = ['updated_at']
    list_per_page = 50


@admin.register(TickData)
class TickDataAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'bid', 'ask', 'spread', 'epoch', 'received_at']
    list_filter = ['symbol', 'received_at']
    search_fields = ['symbol__symbol']
    readonly_fields = ['received_at']
    list_per_page = 50
    date_hierarchy = 'received_at'


@admin.register(DataStreamSession)
class DataStreamSessionAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'status', 'ticks_received', 'error_count', 'connected_at', 'last_tick_at']
    list_filter = ['status', 'connected_at']
    search_fields = ['session_id', 'symbol__symbol']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 50
    date_hierarchy = 'connected_at'


@admin.register(IndicatorValue)
class IndicatorValueAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'indicator_type', 'value', 'timeframe', 'candle_time', 'calculated_at']
    list_filter = ['indicator_type', 'timeframe', 'candle_time']
    search_fields = ['symbol__symbol']
    readonly_fields = ['calculated_at']
    list_per_page = 50
    date_hierarchy = 'candle_time'


@admin.register(TechnicalSignal)
class TechnicalSignalAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'signal_type', 'confidence', 'strength', 'candle_time', 'was_executed']
    list_filter = ['signal_type', 'signal_source', 'candle_time', 'was_executed']
    search_fields = ['symbol__symbol']
    readonly_fields = ['created_at', 'contributing_indicators']
    list_per_page = 50
    date_hierarchy = 'candle_time'


@admin.register(IndicatorProfile)
class IndicatorProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'profile_type', 'require_multiple_indicators', 'min_confidence', 'created_at']
    list_filter = ['profile_type', 'require_multiple_indicators', 'created_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 50


@admin.register(IndicatorAlert)
class IndicatorAlertAdmin(admin.ModelAdmin):
    list_display = ['user', 'symbol', 'indicator_type', 'is_active', 'times_triggered', 'last_triggered']
    list_filter = ['alert_type', 'indicator_type', 'is_active', 'created_at']
    search_fields = ['user__username', 'symbol__symbol']
    readonly_fields = ['created_at', 'updated_at', 'last_triggered']
    list_per_page = 50
