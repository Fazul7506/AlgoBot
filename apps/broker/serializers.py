from rest_framework import serializers
from .models import Broker, BrokerAccount, BrokerConnectionLog, BrokerPermission

class BrokerSerializer(serializers.ModelSerializer):
    class Meta: model = Broker; fields = ["id","name","slug","logo","website","status","created_at"]
class BrokerAccountSerializer(serializers.ModelSerializer):
    broker = BrokerSerializer(read_only=True)
    class Meta: model = BrokerAccount; fields = ["id","broker","broker_account_id","account_type","currency","balance","equity","margin","is_default","is_connected","created_at"]
class BrokerConnectionLogSerializer(serializers.ModelSerializer):
    class Meta: model = BrokerConnectionLog; fields = ["id","broker_account","status","latency","event","created_at"]
class BrokerPermissionSerializer(serializers.ModelSerializer):
    class Meta: model = BrokerPermission; fields = ["id","broker","permission","enabled"]
