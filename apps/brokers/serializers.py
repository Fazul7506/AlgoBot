from rest_framework import serializers
from .models import Broker, BrokerAccount, BrokerConnection, Order, ExecutionReport, Position, TradeReconciliation
class BrokerSerializer(serializers.ModelSerializer):
    class Meta: model=Broker; fields='__all__'
class BrokerAccountSerializer(serializers.ModelSerializer):
    class Meta: model=BrokerAccount; fields='__all__'; read_only_fields=['user']
class BrokerConnectionSerializer(serializers.ModelSerializer):
    class Meta: model=BrokerConnection; fields='__all__'
class OrderSerializer(serializers.ModelSerializer):
    class Meta: model=Order; fields='__all__'; read_only_fields=['user','broker','status','submitted_at','executed_at','broker_order_id']
class ExecutionReportSerializer(serializers.ModelSerializer):
    class Meta: model=ExecutionReport; fields='__all__'
class PositionSerializer(serializers.ModelSerializer):
    class Meta: model=Position; fields='__all__'
class TradeReconciliationSerializer(serializers.ModelSerializer):
    class Meta: model=TradeReconciliation; fields='__all__'
