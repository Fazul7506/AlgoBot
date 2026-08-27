from rest_framework import serializers
from .models import Order, ExecutionLog, ExecutionQueue
from apps.trading.models import Position
from apps.contracts.models import Contract


class OrderSerializer(serializers.ModelSerializer):
    # Keep the wire contract tolerant of the existing BUY/SELL terminal labels,
    # then normalize them before model validation.
    direction = serializers.CharField(max_length=12)
    order_type = serializers.CharField(max_length=32)

    class Meta:
        model = Order
        fields = '__all__'
        read_only_fields = ('user', 'status', 'broker_reference', 'broker_response')

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
