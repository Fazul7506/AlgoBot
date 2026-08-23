from rest_framework import serializers
from .models import Broker, BrokerAccount, BrokerConnection, Order, ExecutionReport, Position, TradeReconciliation


class BrokerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Broker
        fields = "__all__"


class BrokerAccountSerializer(serializers.ModelSerializer):
    broker = serializers.SerializerMethodField()
    broker_account_id = serializers.CharField(source="account_id", read_only=True)
    account_type = serializers.SerializerMethodField()
    is_default = serializers.BooleanField(source="is_preferred", read_only=True)
    is_connected = serializers.SerializerMethodField()

    class Meta:
        model = BrokerAccount
        fields = [
            "id", "user", "broker", "broker_account_id", "account_id", "account_type",
            "currency", "balance", "equity", "margin", "free_margin", "status",
            "is_preferred", "is_default", "is_connected", "last_synced_at", "created_at",
        ]
        read_only_fields = [
            "user", "balance", "equity", "margin", "free_margin", "last_synced_at",
            "broker_account_id", "account_type", "is_default", "is_connected",
        ]

    def get_broker(self, obj):
        return {
            "id": obj.broker_id,
            "name": obj.broker.name,
            "type": obj.broker.broker_type,
            "status": obj.broker.status,
        }

    def get_account_type(self, obj):
        return str((obj.credentials or {}).get("account_type") or "demo").lower()

    def get_is_connected(self, obj):
        return obj.status == "active" and obj.broker.status == "active"


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
    class Meta:
        model = ExecutionReport
        fields = "__all__"


class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = "__all__"


class TradeReconciliationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradeReconciliation
        fields = "__all__"
