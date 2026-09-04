from django.contrib import admin

from .models import (
    Broker,
    BrokerAccount,
    BrokerConnection,
    BrokerConnectionLog,
    BrokerPermission,
    ExecutionReport,
    Order,
    Position,
    TradeReconciliation,
)


@admin.register(Broker)
class BrokerAdmin(admin.ModelAdmin):
    list_display = ["name", "broker_type", "status", "supports_demo", "supports_live", "version"]
    list_filter = ["broker_type", "status", "supports_demo", "supports_live"]
    search_fields = ["name", "broker_type"]
    readonly_fields = ["created_at"]
    list_per_page = 50


@admin.register(BrokerAccount)
class BrokerAccountAdmin(admin.ModelAdmin):
    list_display = [
        "account_id",
        "broker",
        "user",
        "currency",
        "balance",
        "status",
        "token_status",
        "is_preferred",
        "last_synced_at",
    ]
    list_filter = ["broker", "status", "token_status", "is_preferred", "currency"]
    search_fields = ["account_id", "user__username", "user__email", "broker__name"]
    readonly_fields = ["created_at", "last_synced_at", "last_refresh"]
    list_per_page = 50
    date_hierarchy = "created_at"


@admin.register(BrokerConnection)
class BrokerConnectionAdmin(admin.ModelAdmin):
    list_display = ["broker", "broker_account", "status", "latency", "last_ping", "connected_at", "updated_at"]
    list_filter = ["broker", "status"]
    search_fields = ["broker__name", "broker_account__account_id", "broker_account__user__username"]
    readonly_fields = ["updated_at"]
    list_per_page = 50
    date_hierarchy = "updated_at"


@admin.register(BrokerConnectionLog)
class BrokerConnectionLogAdmin(admin.ModelAdmin):
    list_display = ["broker_account", "event", "status", "latency", "created_at"]
    list_filter = ["event", "status", "broker_account__broker", "created_at"]
    search_fields = ["broker_account__account_id", "broker_account__user__username", "event"]
    readonly_fields = ["created_at"]
    list_per_page = 50
    date_hierarchy = "created_at"


@admin.register(BrokerPermission)
class BrokerPermissionAdmin(admin.ModelAdmin):
    list_display = ["broker", "permission", "enabled"]
    list_filter = ["broker", "enabled"]
    search_fields = ["broker__name", "permission"]
    list_per_page = 50


@admin.register(Order)
class BrokerOrderAdmin(admin.ModelAdmin):
    list_display = [
        "symbol",
        "direction",
        "order_type",
        "contract_type",
        "status",
        "stake",
        "quantity",
        "broker_order_id",
        "submitted_at",
        "executed_at",
    ]
    list_filter = ["broker", "status", "direction", "order_type", "contract_type", "submitted_at", "executed_at"]
    search_fields = [
        "symbol",
        "client_order_id",
        "broker_order_id",
        "account__account_id",
        "user__username",
    ]
    readonly_fields = ["created_at", "updated_at", "submitted_at", "executed_at"]
    list_per_page = 50
    date_hierarchy = "created_at"


@admin.register(ExecutionReport)
class ExecutionReportAdmin(admin.ModelAdmin):
    list_display = ["order", "status", "execution_price", "requested_price", "slippage", "fees", "latency", "created_at"]
    list_filter = ["status", "order__broker", "created_at"]
    search_fields = ["order__symbol", "order__broker_order_id", "order__user__username"]
    readonly_fields = ["created_at"]
    list_per_page = 50
    date_hierarchy = "created_at"


@admin.register(Position)
class BrokerPositionAdmin(admin.ModelAdmin):
    list_display = ["symbol", "direction", "size", "entry_price", "current_price", "profit", "status", "account", "opened_at", "closed_at"]
    list_filter = ["broker", "status", "direction", "opened_at", "closed_at"]
    search_fields = ["symbol", "account__account_id", "account__user__username"]
    readonly_fields = ["opened_at", "closed_at"]
    list_per_page = 50
    date_hierarchy = "opened_at"


@admin.register(TradeReconciliation)
class TradeReconciliationAdmin(admin.ModelAdmin):
    list_display = ["broker", "matched", "repaired", "timestamp"]
    list_filter = ["broker", "matched", "repaired", "timestamp"]
    search_fields = ["broker__name"]
    readonly_fields = ["timestamp"]
    list_per_page = 50
    date_hierarchy = "timestamp"
