from django.contrib import admin
from .models import Broker, BrokerAccount, BrokerToken, BrokerConnectionLog, BrokerPermission

@admin.register(Broker)
class BrokerAdmin(admin.ModelAdmin): list_display = ("name", "slug", "status", "created_at")
@admin.register(BrokerAccount)
class BrokerAccountAdmin(admin.ModelAdmin): list_display = ("user", "broker", "broker_account_id", "account_type", "is_connected", "is_default")
@admin.register(BrokerToken)
class BrokerTokenAdmin(admin.ModelAdmin): list_display = ("broker_account", "expires_at", "last_refresh", "status")
@admin.register(BrokerConnectionLog)
class BrokerConnectionLogAdmin(admin.ModelAdmin): list_display = ("broker_account", "status", "event", "latency", "created_at")
@admin.register(BrokerPermission)
class BrokerPermissionAdmin(admin.ModelAdmin): list_display = ("broker", "permission", "enabled")
