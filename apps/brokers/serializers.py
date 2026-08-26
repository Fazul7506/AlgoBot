from django.conf import settings
from rest_framework import serializers
from .models import Broker, BrokerAccount, BrokerConnection, Order, ExecutionReport, Position, TradeReconciliation


class BrokerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Broker
        fields = "__all__"


class BrokerAccountSerializer(serializers.ModelSerializer):
    broker = serializers.SerializerMethodField()
    broker_name = serializers.CharField(source="broker.name", read_only=True)
    broker_account_id = serializers.CharField(source="account_id", read_only=True)
    account_type = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    branding = serializers.SerializerMethodField()
    is_default = serializers.BooleanField(source="is_preferred", read_only=True)
    is_connected = serializers.SerializerMethodField()
    credential_status = serializers.CharField(read_only=True)
    data_freshness = serializers.SerializerMethodField()
    switch_enabled = serializers.SerializerMethodField()

    class Meta:
        model = BrokerAccount
        fields = [
            "id", "user", "broker", "broker_name", "broker_account_id", "account_id",
            "account_type", "avatar_url", "display_name", "branding", "currency", "balance", "equity",
            "margin", "free_margin", "status", "is_preferred", "is_default", "is_connected",
            "credential_status", "last_synced_at", "data_freshness", "switch_enabled", "created_at",
        ]
        read_only_fields = [
            "user", "balance", "equity", "margin", "free_margin", "last_synced_at",
            "broker_account_id", "account_type", "avatar_url", "display_name", "branding", "is_default",
            "is_connected", "data_freshness", "switch_enabled",
        ]

    def _is_deriv(self, obj):
        return str(obj.broker.broker_type or "").lower() == "deriv"

    def get_broker(self, obj):
        metadata = obj.broker.metadata or {}
        return {
            "id": obj.broker_id,
            "name": obj.broker.name,
            "type": obj.broker.broker_type,
            "status": obj.broker.status,
            "avatar_url": metadata.get("avatar_url") or "",
        }

    def get_account_type(self, obj):
        credentials = obj.credentials or {}
        value = str(credentials.get("account_type") or "").lower()
        return value if value in {"real", "demo"} else "unknown"

    def get_avatar_url(self, obj):
        credentials = obj.credentials or {}
        metadata = obj.broker.metadata or {}
        # Prefer the actual broker-supplied account avatar. Never replace it
        # with a fabricated remote image. The frontend supplies a local,
        # deterministic Deriv fallback when the broker supplies no avatar.
        return str(credentials.get("avatar_url") or metadata.get("avatar_url") or "")

    def get_display_name(self, obj):
        return f"{obj.broker.name} · {obj.account_id}"

    def get_branding(self, obj):
        if self._is_deriv(obj):
            account_type = self.get_account_type(obj)
            return {
                "provider": "Deriv",
                "powered_by": "Deriv",
                "country_code": "US",
                "flag": "🇺🇸",
                "account_type": account_type,
                "label": "Deriv Demo Account" if account_type == "demo" else "Deriv Real Account" if account_type == "real" else "Deriv Account",
            }
        return {
            "provider": obj.broker.name,
            "powered_by": obj.broker.name,
            "country_code": "",
            "flag": "",
            "account_type": self.get_account_type(obj),
            "label": obj.broker.name,
        }

    def get_is_connected(self, obj):
        return obj.is_connection_eligible

    def get_data_freshness(self, obj):
        if not obj.last_synced_at:
            return {"state": "never_synced", "seconds": None}
        from django.utils import timezone
        seconds = max(0, int((timezone.now() - obj.last_synced_at).total_seconds()))
        return {"state": "fresh" if seconds <= 60 else "stale", "seconds": seconds}

    def get_switch_enabled(self, obj):
        return bool(settings.ENABLE_BROKER_ACCOUNT_SWITCH)


class BrokerConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrokerConnection
        fields = "__all__"


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = "__all__"
        read_only_fields = ["user", "broker", "status", "submitted_at", "executed_at", "broker_order_id"]


class ExecutionReportSerializer(serializers.ModelSerializer):
    symbol = serializers.CharField(source="order.symbol", read_only=True)
    direction = serializers.CharField(source="order.direction", read_only=True)
    broker_order_id = serializers.CharField(source="order.broker_order_id", read_only=True)

    class Meta:
        model = ExecutionReport
        fields = [
            "id", "order", "execution_price", "requested_price", "slippage", "latency", "fees",
            "status", "raw_report", "created_at", "symbol", "direction", "broker_order_id",
        ]


class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = "__all__"


class TradeReconciliationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradeReconciliation
        fields = "__all__"
