from rest_framework import serializers
from .models import Order, ExecutionLog, ExecutionQueue, ReconciliationEvent, BrokerTradeHistory
from apps.trading.models import Position
from apps.contracts.models import Contract


class OrderSerializer(serializers.ModelSerializer):
    # Keep the wire contract tolerant of the existing BUY/SELL terminal labels.
    direction = serializers.CharField(max_length=12)
    order_type = serializers.CharField(max_length=32)
    contract_type = serializers.CharField(max_length=40, required=False, allow_blank=True)
    duration = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    duration_unit = serializers.ChoiceField(required=False, allow_blank=True, choices=['s','m','h','d','t'])

    class Meta:
        model = Order
        fields = [
            'id', 'user', 'broker_account', 'symbol', 'strategy', 'direction',
            'order_type', 'contract_type', 'duration', 'duration_unit', 'stake', 'price', 'status', 'broker_reference',
            'client_request_id', 'validation_context', 'broker_payload', 'submitted_at', 'executed_at',
            'broker_response', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'status', 'broker_reference', 'validation_context',
            'broker_payload', 'broker_response', 'submitted_at', 'executed_at', 'created_at', 'updated_at'
        ]

    def validate_direction(self, value):
        value = str(value).strip().lower()
        allowed = {choice[0] for choice in Order.DIRECTION_CHOICES}
        if value not in allowed:
            raise serializers.ValidationError(f'Unsupported order direction: {value}')
        return value

    def validate_order_type(self, value):
        value = str(value).strip().lower()
        allowed = {choice[0] for choice in Order.ORDER_TYPE_CHOICES}
        if value not in allowed:
            raise serializers.ValidationError(f'Unsupported order type: {value}')
        return value

    def validate_broker_account(self, account):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated or account.user_id != user.id:
            raise serializers.ValidationError('The selected broker account does not belong to the authenticated user.')
        if account.status != 'active' or account.broker.status != 'active':
            raise serializers.ValidationError('The selected broker account is not active.')
        return account


class PositionSerializer(serializers.ModelSerializer):
    roi = serializers.DecimalField(max_digits=18, decimal_places=8, read_only=True)
    class Meta:
        model = Position
        fields = '__all__'


class ContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contract
        fields = '__all__'


class ExecutionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExecutionLog
        fields = '__all__'


class ExecutionQueueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExecutionQueue
        fields = '__all__'


class ReconciliationEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationEvent
        fields = '__all__'
        read_only_fields = ('user', 'broker_account', 'detected_at', 'reviewed_at', 'reviewed_by')


class BrokerTradeHistorySerializer(serializers.ModelSerializer):
    ai = serializers.SerializerMethodField()

    class Meta:
        model = BrokerTradeHistory
        fields = [field.name for field in BrokerTradeHistory._meta.fields] + ["ai"]
        read_only_fields = tuple(field.name for field in BrokerTradeHistory._meta.fields)

    def get_ai(self, obj):
        linked = (self.context.get("ai_by_contract") or {}).get(obj.broker_contract_id) or {}
        context = linked.get("context") or {}
        ai = context.get("ai_consensus") or context.get("ai_decision")
        if not ai:
            return None
        return {
            "source": context.get("ai_source") or "AI analysis",
            "prediction": context.get("ai_prediction") or ai.get("prediction") or ai.get("decision"),
            "confidence": ai.get("confidence"),
            "analysis_timestamp": linked.get("created_at"),
        }
