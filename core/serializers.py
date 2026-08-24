"""Serializers for core models and API endpoints."""
from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from core.models import (
    UserProfile, Subscription, BotSettings, AuditLog,
    Invoice, Payment, ReferralReward, EncryptedCredential
)


class UserSerializer(serializers.ModelSerializer):
    """Basic user information serializer"""
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id']


class UserProfileSerializer(serializers.ModelSerializer):
    """User profile with extended information"""
    user = UserSerializer(read_only=True)
    deriv_account_id = serializers.SerializerMethodField()
    
    class Meta:
        model = UserProfile
        fields = [
            'id', 'user', 'bio', 'phone', 'country', 'timezone',
            'email_verified', 'two_factor_enabled', 'notifications_enabled',
            'email_notifications_enabled', 'telegram_notifications_enabled',
            'telegram_chat_id', 'telegram_username', 'brevo_sender_email',
            'avatar_url', 'referral_code', 'referral_credits',
            'last_login_at', 'created_at', 'updated_at', 'deriv_account_id'
        ]
        read_only_fields = ['id', 'user', 'email_verified', 'created_at', 'updated_at']

    def get_deriv_account_id(self, obj):
        """Get connected Deriv account ID if available"""
        try:
            return obj.user.deriv_account.account_id
        except:
            return None


class SubscriptionSerializer(serializers.ModelSerializer):
    """Subscription plan information"""
    class Meta:
        model = Subscription
        fields = [
            'id', 'plan', 'max_strategies', 'max_concurrent_trades',
            'api_calls_per_day', 'is_active', 'price_cents', 'currency',
            'created_at', 'expires_at'
        ]
        read_only_fields = ['id', 'created_at']


class BotSettingsSerializer(serializers.ModelSerializer):
    """Bot settings and trading preferences"""
    class Meta:
        model = BotSettings
        fields = [
            'id', 'is_enabled', 'status', 'default_strategy',
            'max_daily_loss_pct', 'risk_per_trade_pct',
            'max_concurrent_trades', 'min_win_rate',
            'is_paper_trading', 'paper_balance',
            'email_notifications_enabled', 'telegram_notifications_enabled',
            'telegram_chat_id', 'telegram_username',
            'brevo_sender_email', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'status', 'created_at', 'updated_at']


class AuditLogSerializer(serializers.ModelSerializer):
    """Audit log entry"""
    username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = AuditLog
        fields = [
            'id', 'user', 'username', 'path', 'method', 'status_code',
            'ip_address', 'user_agent', 'error', 'created_at'
        ]
        read_only_fields = ['id', 'user', 'created_at']


class InvoiceSerializer(serializers.ModelSerializer):
    """Invoice information"""
    class Meta:
        model = Invoice
        fields = [
            'id', 'user', 'external_id', 'amount_cents', 'currency',
            'paid', 'created_at'
        ]
        read_only_fields = ['id', 'user', 'created_at']


class PaymentSerializer(serializers.ModelSerializer):
    """Payment record"""
    class Meta:
        model = Payment
        fields = [
            'id', 'user', 'external_id', 'amount_cents', 'currency',
            'status', 'created_at'
        ]
        read_only_fields = ['id', 'user', 'created_at']


class ReferralRewardSerializer(serializers.ModelSerializer):
    """Referral reward record"""
    referrer_username = serializers.CharField(source='referrer.username', read_only=True)
    referee_username = serializers.CharField(source='referee.username', read_only=True)
    
    class Meta:
        model = ReferralReward
        fields = [
            'id', 'referrer', 'referrer_username', 'referee', 'referee_username',
            'amount_credits', 'awarded_at'
        ]
        read_only_fields = ['id', 'awarded_at']


class EncryptedCredentialSerializer(serializers.ModelSerializer):
    """Encrypted credential (value is never returned)"""
    class Meta:
        model = EncryptedCredential
        fields = [
            'id', 'service_name', 'credential_type', 'updated_at'
        ]
        read_only_fields = ['id', 'updated_at']


class RegisterSerializer(serializers.ModelSerializer):
    """User registration serializer"""
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password]
    )
    password_confirm = serializers.CharField(write_only=True, required=True)
    
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password', 'password_confirm']
        extra_kwargs = {
            'email': {'required': True},
        }
    
    def validate(self, data):
        """Validate passwords match"""
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password": "Passwords must match."})
        return data
    
    def create(self, validated_data):
        """Create user and related objects"""
        validated_data.pop('password_confirm', None)
        user = User.objects.create_user(**validated_data)
        
        # Create related objects via signals
        return user


class LoginSerializer(serializers.Serializer):
    """User login serializer"""
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    
    def validate(self, data):
        """Authenticate user"""
        from django.contrib.auth import authenticate
        username = data['username']
        password = data['password']

        user = authenticate(username=username, password=password)
        if not user:
            # Fallback if the user submitted an email address instead of a username
            try:
                user_obj = User.objects.get(email=username)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                user = None

        if not user:
            raise serializers.ValidationError("Invalid username or password")
        data['user'] = user
        return data


class PasswordResetSerializer(serializers.Serializer):
    """Password reset request serializer"""
    email = serializers.EmailField()
    
    def validate_email(self, value):
        """Check if user exists"""
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("No user found with this email address.")
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Password reset confirmation serializer"""
    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True,
        validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(write_only=True)
    
    def validate(self, data):
        """Validate passwords match"""
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError({"new_password": "Passwords must match."})
        return data


class ChangePasswordSerializer(serializers.Serializer):
    """Change password serializer"""
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(
        write_only=True,
        validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(write_only=True)
    
    def validate(self, data):
        """Validate passwords match"""
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError({"new_password": "Passwords must match."})
        return data
