from rest_framework import serializers
from .models import APIKey, Webhook, Plugin, SDKRelease, Integration


class APIKeyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    permissions = serializers.ListField(child=serializers.CharField(), required=False)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class APIKeySerializer(serializers.ModelSerializer):
    """Return only a non-sensitive key identifier; never expose secret material."""
    key = serializers.SerializerMethodField()
    key_hint = serializers.SerializerMethodField()

    class Meta:
        model = APIKey
        fields = ["id", "name", "key", "key_hint", "permissions", "expires_at", "last_used", "status", "created_at"]
        read_only_fields = fields

    def get_key(self, obj):
        raw = str(obj.key or "")
        if not raw:
            return "••••••••"
        prefix = raw.split("_", 1)[0] + "_" if "_" in raw else ""
        suffix = raw[-4:] if len(raw) >= 4 else ""
        return f"{prefix}••••••••••••{suffix}"

    def get_key_hint(self, obj):
        raw = str(obj.key or "")
        return raw[-4:] if len(raw) >= 4 else ""


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
    configuration = serializers.SerializerMethodField()

    class Meta:
        model = Integration
        fields = "__all__"

    def get_configuration(self, obj):
        sensitive = {"secret", "token", "api_key", "apikey", "access_token", "refresh_token", "client_secret", "password", "private_key"}

        def redact(value):
            if isinstance(value, dict):
                return {key: ("••••••••" if str(key).lower() in sensitive else redact(item)) for key, item in value.items()}
            if isinstance(value, list):
                return [redact(item) for item in value]
            return value

        return redact(obj.configuration or {})
