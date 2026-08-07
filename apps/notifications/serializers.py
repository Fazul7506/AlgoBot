from rest_framework import serializers
from .models import Notification, NotificationTemplate, NotificationPreference, DeliveryLog, NotificationRule, Broadcast
class NotificationSerializer(serializers.ModelSerializer):
    class Meta: model=Notification; fields="__all__"; read_only_fields=("user",)
class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta: model=NotificationTemplate; fields="__all__"
class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta: model=NotificationPreference; fields="__all__"; read_only_fields=("user",)
class DeliveryLogSerializer(serializers.ModelSerializer):
    class Meta: model=DeliveryLog; fields="__all__"
class NotificationRuleSerializer(serializers.ModelSerializer):
    class Meta: model=NotificationRule; fields="__all__"
class BroadcastSerializer(serializers.ModelSerializer):
    class Meta: model=Broadcast; fields="__all__"
