from django.contrib import admin

from .models import ExecutionLog, ExecutionQueue, Order, ReconciliationEvent


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "symbol", "direction", "order_type", "status", "stake",
        "broker_account", "broker_reference", "client_request_id",
        "created_at", "updated_at",
    ]
    list_filter = ["status", "direction", "order_type", "broker_account__broker", "created_at"]
    search_fields = [
        "symbol", "strategy", "broker_reference", "client_request_id",
        "user__username", "broker_account__account_id",
    ]
    readonly_fields = [
        "user", "broker_account", "symbol", "strategy", "direction",
        "order_type", "contract_type", "duration", "duration_unit", "stake",
        "price", "status", "broker_reference", "client_request_id",
        "validation_context", "broker_payload", "broker_response",
        "submitted_at", "executed_at", "created_at", "updated_at",
    ]
    list_per_page = 50
    date_hierarchy = "created_at"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(ExecutionLog)
class ExecutionLogAdmin(admin.ModelAdmin):
    list_display = ["order", "event", "status", "latency", "created_at"]
    list_filter = ["event", "status", "created_at"]
    search_fields = ["order__symbol", "order__broker_reference", "order__user__username", "message"]
    readonly_fields = ["order", "event", "status", "latency", "message", "broker_response", "created_at"]
    list_per_page = 50
    date_hierarchy = "created_at"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(ExecutionQueue)
class ExecutionQueueAdmin(admin.ModelAdmin):
    list_display = ["order", "priority", "attempts", "status", "queue_type", "next_retry", "created_at", "updated_at"]
    list_filter = ["status", "queue_type", "priority", "created_at"]
    search_fields = ["order__symbol", "order__broker_reference", "order__client_request_id"]
    readonly_fields = ["order", "priority", "attempts", "status", "queue_type", "next_retry", "created_at", "updated_at"]
    list_per_page = 50
    date_hierarchy = "created_at"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(ReconciliationEvent)
class ReconciliationEventAdmin(admin.ModelAdmin):
    list_display = [
        "broker_account", "status", "discrepancy_type", "broker_reference",
        "symbol", "summary", "detected_at", "reviewed_at", "reviewed_by",
    ]
    list_filter = ["status", "discrepancy_type", "broker_account__broker", "detected_at"]
    search_fields = [
        "broker_reference", "symbol", "summary",
        "broker_account__account_id", "user__username",
    ]
    readonly_fields = [
        "user", "broker_account", "status", "discrepancy_type",
        "broker_reference", "symbol", "summary", "details",
        "detected_at", "reviewed_at", "reviewed_by",
    ]
    list_per_page = 50
    date_hierarchy = "detected_at"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
