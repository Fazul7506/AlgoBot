from rest_framework import serializers
from .models import Order, ExecutionLog, ExecutionQueue
from apps.trading.models import Position
from apps.contracts.models import Contract
class OrderSerializer(serializers.ModelSerializer):
    class Meta: model=Order; fields='__all__'; read_only_fields=('user','status','broker_reference','broker_response')
class PositionSerializer(serializers.ModelSerializer):
    roi=serializers.DecimalField(max_digits=18,decimal_places=8,read_only=True)
    class Meta: model=Position; fields='__all__'
class ContractSerializer(serializers.ModelSerializer):
    class Meta: model=Contract; fields='__all__'
class ExecutionLogSerializer(serializers.ModelSerializer):
    class Meta: model=ExecutionLog; fields='__all__'
class ExecutionQueueSerializer(serializers.ModelSerializer):
    class Meta: model=ExecutionQueue; fields='__all__'
