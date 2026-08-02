from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from core.models import UserProfile, Subscription, BotSettings


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']


class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    deriv_account_id = serializers.SerializerMethodField()
    
    class Meta:
        model = UserProfile
        fields = [
            'id', 'user', 'bio', 'phone', 'country', 'timezone',
            'email_verified', 'two_factor_enabled', 'notifications_enabled',
            'email_notifications_enabled', 'telegram_notifications_enabled',
            'telegram_chat_id', 'telegram_username', 'brevo_sender_email',
            'avatar_url', 'last_login_at', 'created_at', 'updated_at',
            'deriv_account_id'
        ]
        read_only_fields = ['id', 'user', 'email_verified', 'created_at', 'updated_at']

    def get_deriv_account_id(self, obj):
        return getattr(obj.user, 'derivaccount', None) and obj.user.derivaccount.account_id or None


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = [
            'id', 'plan', 'max_strategies', 'max_concurrent_trades',
            'api_calls_per_day', 'is_active', 'created_at', 'expires_at'
        ]
        read_only_fields = ['id', 'created_at']


class BotSettingsSerializer(serializers.ModelSerializer):
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


class RegisterSerializer(serializers.ModelSerializer):
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
            'first_name': {'required': True},
            'last_name': {'required': True},
            'email': {'required': True},
        }
    
    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password": "Passwords must match."})
        return data
    
    def create(self, validated_data):
        validated_data.pop('password_confirm', None)
        user = User.objects.create_user(**validated_data)
        
        # Create related objects
        UserProfile.objects.create(user=user)
        Subscription.objects.create(user=user)
        BotSettings.objects.create(user=user)
        
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    
    def validate(self, data):
        from django.contrib.auth import authenticate
        username = data['username']
        password = data['password']

        user = authenticate(username=username, password=password)
        if not user:
            # Fallback if the user submitted an email address instead of a username.
            from django.contrib.auth.models import User
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
    email = serializers.EmailField()
    
    def validate_email(self, value):
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("No user found with this email address.")
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True,
        validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(write_only=True)
    
    def validate(self, data):
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError({"new_password": "Passwords must match."})
        return data


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(
        write_only=True,
        validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(write_only=True)
    
    def validate(self, data):
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError({"new_password": "Passwords must match."})
        return data
