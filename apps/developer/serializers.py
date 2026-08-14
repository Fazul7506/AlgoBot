from rest_framework import serializers
from .models import APIKey, Webhook, Plugin, SDKRelease, Integration

class APIKeyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    permissions = serializers.ListField(child=serializers.CharField(), required=False)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

class APIKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKey
        fields = ["id", "name", "key", "permissions", "expires_at", "last_used", "status", "created_at"]
        read_only_fields = fields

class WebhookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Webhook
        fields = ["id", "url", "events", "status", "created_at", "updated_at"]
        read_only_fields = ["id", "status", "created_at", "updated_at"]

class PluginSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plugin
        fields = "__all__"

class SDKReleaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = SDKRelease
        fields = "__all__"

class IntegrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Integration
        fields = "__all__"
