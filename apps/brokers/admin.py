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
    """Broker account state is application-managed; credentials never render here."""
    list_display = [
        "account_id", "broker", "user", "currency", "balance",
        "status", "token_status", "last_synced_at",
    ]
    list_filter = ["broker", "status", "token_status", "currency"]
    search_fields = ["account_id", "user__username", "user__email", "broker__name"]
    readonly_fields = [
        "account_id", "broker", "user", "currency", "balance", "equity",
        "margin", "free_margin", "status", "token_status", "expires_at",
        "last_refresh", "last_synced_at", "created_at",
    ]
    exclude = ["credentials", "access_token", "refresh_token"]
    list_per_page = 50
    date_hierarchy = "created_at"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(BrokerConnection)
class BrokerConnectionAdmin(admin.ModelAdmin):
    list_display = ["broker", "broker_account", "status", "latency", "last_ping", "connected_at", "updated_at"]
    list_filter = ["broker", "status"]
    search_fields = ["broker__name", "broker_account__account_id", "broker_account__user__username"]
    readonly_fields = [
        "broker", "broker_account", "status", "latency", "last_ping",
        "heartbeat", "connected_at", "updated_at",
    ]
    list_per_page = 50
    date_hierarchy = "updated_at"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(BrokerConnectionLog)
class BrokerConnectionLogAdmin(admin.ModelAdmin):
    list_display = ["broker_account", "event", "status", "latency", "created_at"]
    list_filter = ["event", "status", "broker_account__broker", "created_at"]
    search_fields = ["broker_account__account_id", "broker_account__user__username", "event"]
    readonly_fields = ["broker_account", "event", "status", "latency", "created_at"]
    list_per_page = 50
    date_hierarchy = "created_at"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(BrokerPermission)
class BrokerPermissionAdmin(admin.ModelAdmin):
    list_display = ["broker", "permission", "enabled"]
    list_filter = ["broker", "enabled"]
    search_fields = ["broker__name", "permission"]
    list_per_page = 50


@admin.register(Order)
class BrokerOrderAdmin(admin.ModelAdmin):
    list_display = [
        "symbol", "direction", "order_type", "contract_type", "status",
        "stake", "quantity", "broker_order_id", "submitted_at", "executed_at",
    ]
    list_filter = ["broker", "status", "direction", "order_type", "contract_type", "submitted_at", "executed_at"]
    search_fields = ["symbol", "client_order_id", "broker_order_id", "account__account_id", "user__username"]
    readonly_fields = [
        "user", "broker", "account", "strategy", "symbol", "direction",
        "order_type", "contract_type", "stake", "quantity", "price", "status",
        "client_order_id", "broker_order_id", "routing_context", "submitted_at",
        "executed_at", "created_at", "updated_at",
    ]
    list_per_page = 50
    date_hierarchy = "created_at"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(ExecutionReport)
class ExecutionReportAdmin(admin.ModelAdmin):
    list_display = ["order", "status", "execution_price", "requested_price", "slippage", "fees", "latency", "created_at"]
    list_filter = ["status", "order__broker", "created_at"]
    search_fields = ["order__symbol", "order__broker_order_id", "order__user__username"]
    readonly_fields = [
        "order", "execution_price", "requested_price", "slippage",
        "latency", "fees", "status", "raw_report", "created_at",
    ]
    list_per_page = 50
    date_hierarchy = "created_at"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(Position)
class BrokerPositionAdmin(admin.ModelAdmin):
    list_display = [
        "symbol", "direction", "size", "entry_price", "current_price",
        "profit", "status", "account", "opened_at", "closed_at",
    ]
    list_filter = ["broker", "status", "direction", "opened_at", "closed_at"]
    search_fields = ["symbol", "account__account_id", "account__user__username"]
    readonly_fields = [
        "symbol", "direction", "size", "entry_price", "current_price",
        "profit", "status", "account", "broker", "opened_at", "closed_at",
    ]
    list_per_page = 50
    date_hierarchy = "opened_at"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(TradeReconciliation)
class TradeReconciliationAdmin(admin.ModelAdmin):
    list_display = ["broker", "matched", "repaired", "timestamp"]
    list_filter = ["broker", "matched", "repaired", "timestamp"]
    search_fields = ["broker__name"]
    readonly_fields = ["broker", "matched", "repaired", "timestamp"]
    list_per_page = 50
    date_hierarchy = "timestamp"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
