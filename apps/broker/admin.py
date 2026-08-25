from django.contrib import admin

from .models import (
    Broker,
    BrokerAccount,
    BrokerConnectionLog,
    BrokerPermission,
)


@admin.register(Broker)
class BrokerAdmin(admin.ModelAdmin):
    list_display = ("name", "broker_type", "status", "created_at")
    search_fields = ("name", "broker_type")
    list_filter = ("broker_type", "status")


@admin.register(BrokerAccount)
class BrokerAccountAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "broker",
        "account_id",
        "currency",
        "status",
        "is_preferred",
        "token_status",
    )
    search_fields = ("account_id", "user__username", "user__email", "broker__name")
    list_filter = ("broker", "status", "token_status", "is_preferred")


@admin.register(BrokerConnectionLog)
class BrokerConnectionLogAdmin(admin.ModelAdmin):
    list_display = ("broker_account", "status", "event", "latency", "created_at")
    search_fields = ("event", "status", "broker_account__account_id")
    list_filter = ("status", "event")


@admin.register(BrokerPermission)
class BrokerPermissionAdmin(admin.ModelAdmin):
    list_display = ("broker", "permission", "enabled")
    search_fields = ("permission", "broker__name")
    list_filter = ("enabled", "broker")
