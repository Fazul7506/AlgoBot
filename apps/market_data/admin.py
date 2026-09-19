from django.contrib import admin

from .models import Candle, CandleBackfillEvent, CandleBackfillRun, MarketSnapshot, MarketStatistics, MarketSymbol, Tick


class CandleBackfillEventInline(admin.TabularInline):
    model = CandleBackfillEvent
    extra = 0
    can_delete = False
    fields = ("created_at", "level", "event_type", "message", "symbol", "timeframe", "task_id", "worker_hostname")
    readonly_fields = fields
    ordering = ("-created_at",)
    classes = ("collapse",)


@admin.register(CandleBackfillRun)
class CandleBackfillRunAdmin(admin.ModelAdmin):
    change_list_template = "admin/market_data/candlebackfillrun/change_list.html"
    list_display = (
        "scope", "status", "progress_display", "celery_state", "heartbeat_display", "count", "current_symbol", "current_timeframe",
        "task_id", "requested_by", "requested_at", "started_at", "completed_at",
    )
    list_filter = ("scope", "status")
    search_fields = ("scope", "symbol", "task_id", "error", "requested_by__username")
    readonly_fields = (
        "scope", "status", "progress_display", "celery_state", "count", "symbol",
        "task_id", "requested_by", "requested_at", "started_at", "completed_at",
        "result", "error",
    )
    ordering = ("-requested_at",)
    inlines = (CandleBackfillEventInline,)

    @admin.display(description="Progress", ordering="status")
    def progress_display(self, obj):
        result = obj.result or {}
        percent = result.get("percent", 0)
        completed = result.get("symbols_completed", 0)
        total = result.get("symbols_total", 0)
        return f"{percent}% · {completed}/{total}" if total else "—"

    @admin.display(description="Worker", ordering="status")
    def celery_state(self, obj):
        if obj.status == "completed":
            return "SUCCESS"
        if obj.status == "failed":
            return "FAILURE"
        if obj.started_at:
            return "STARTED"
        if obj.task_id:
            return "DISPATCHING"
        return "DISPATCHING"

    @admin.display(description="Heartbeat")
    def heartbeat_display(self, obj):
        return obj.last_heartbeat_at or "—"


@admin.register(MarketSymbol)
class MarketSymbolAdmin(admin.ModelAdmin):
    list_display = ("symbol", "display_name", "market", "sub_market", "broker", "is_active", "is_tradable")
    list_filter = ("broker", "market", "is_active", "is_tradable")
    search_fields = ("symbol", "display_name", "sub_market")
    list_editable = ("is_active", "is_tradable")


@admin.register(Candle)
class CandleAdmin(admin.ModelAdmin):
    list_display = ("symbol", "timeframe", "epoch", "open", "high", "low", "close", "volume")
    list_filter = ("timeframe", "symbol__market")
    search_fields = ("symbol__symbol",)
    ordering = ("-epoch",)
    list_per_page = 100


@admin.register(Tick)
class TickAdmin(admin.ModelAdmin):
    list_display = ("symbol", "epoch", "quote", "bid", "ask", "spread", "volume", "received_at")
    list_filter = ("symbol__market",)
    search_fields = ("symbol__symbol",)
    ordering = ("-epoch",)
    list_per_page = 100


@admin.register(MarketSnapshot)
class MarketSnapshotAdmin(admin.ModelAdmin):
    list_display = ("symbol", "last_price", "bid", "ask", "spread", "change_percent", "volume", "timestamp")
    list_filter = ("symbol__market",)
    search_fields = ("symbol__symbol", "symbol__display_name")
    ordering = ("-timestamp",)


@admin.register(MarketStatistics)
class MarketStatisticsAdmin(admin.ModelAdmin):
    list_display = ("symbol", "tick_count", "average_spread", "highest_price", "lowest_price", "market_volatility", "created_at")
    list_filter = ("symbol__market",)
    search_fields = ("symbol__symbol", "symbol__display_name")
    ordering = ("-created_at",)
