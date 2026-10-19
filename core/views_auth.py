"""API views for authentication and user management."""
import logging
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.exceptions import TokenError
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.contrib.auth.password_validation import validate_password
from django.conf import settings
from datetime import timedelta
import secrets

from core.models import UserProfile, Subscription, BotSettings, PasswordResetToken
from core.serializers import UserProfileSerializer, SubscriptionSerializer, BotSettingsSerializer

logger = logging.getLogger(__name__)
from core.auth_rate_limit import allow_auth_attempt


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    identifier = serializers.CharField(required=False, write_only=True)
    email = serializers.EmailField(required=False, write_only=True)
    two_factor_code = serializers.CharField(required=False, write_only=True, allow_blank=True, max_length=32)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep the legacy username field while allowing email/identifier clients.
        self.fields[self.username_field].required = False

    def validate(self, attrs):
        two_factor_code = str(attrs.pop("two_factor_code", "") or "")
        identifier = str(
            attrs.pop('identifier', None)
            or attrs.pop('email', None)
            or attrs.get(self.username_field)
            or ''
        ).strip()
        if not identifier:
            raise serializers.ValidationError({self.username_field: 'Username or email is required.'})
        if '@' in identifier:
            matches = User.objects.filter(email__iexact=identifier)
            if matches.count() != 1:
                raise serializers.ValidationError('Invalid credentials.')
            attrs[self.username_field] = matches.first().get_username()
        elif not User.objects.filter(**{self.username_field: identifier}).exists():
            matches = User.objects.filter(**{f'{self.username_field}__iexact': identifier})
            if matches.count() == 1:
                attrs[self.username_field] = matches.first().get_username()
        data = super().validate(attrs)
        profile = UserProfile.objects.filter(user=self.user).first()
        if not profile or not profile.email_verified:
            raise serializers.ValidationError("Please verify your email before signing in.")
        if profile.two_factor_enabled:
            from core.services.two_factor_service import verify_user_code
            if not two_factor_code:
                raise serializers.ValidationError({"code": "two_factor_required", "detail": "A valid authenticator or recovery code is required."})
            if not verify_user_code(profile, two_factor_code, consume_recovery=True):
                raise serializers.ValidationError({"code": "two_factor_invalid", "detail": "The authenticator or recovery code is invalid."})
        from core.broker_onboarding import has_authorized_broker_connection
        from django.urls import reverse
        broker_setup_required = not has_authorized_broker_connection(self.user)
        data["broker_setup_required"] = broker_setup_required
        data["next_url"] = reverse(
            "broker_marketplace_page" if broker_setup_required else "dashboard_page"
        )
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['email'] = user.email
        return token


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    """Refresh only active accounts whose local email remains verified."""

    def validate(self, attrs):
        raw_refresh = attrs.get("refresh")
        try:
            refresh = RefreshToken(raw_refresh)
            user_id = refresh.get(api_settings.USER_ID_CLAIM)
            user = User.objects.filter(
                **{api_settings.USER_ID_FIELD: user_id},
                is_active=True,
            ).first()
        except (TokenError, TypeError, ValueError):
            user = None
        if user is None:
            raise serializers.ValidationError("The refresh token is invalid or the account is inactive.")

        from core.broker_onboarding import has_verified_account_email
        if not has_verified_account_email(user):
            raise serializers.ValidationError({
                "code": "email_verification_required",
                "detail": "Verify your AlgoBot email before refreshing workspace credentials.",
            })

        # Let SimpleJWT perform expiry, blacklist, rotation and token-family
        # validation after the account eligibility checks above.
        data = super().validate(attrs)
        from core.broker_onboarding import has_authorized_broker_connection
        broker_setup_required = not has_authorized_broker_connection(user)
        data["broker_setup_required"] = broker_setup_required
        from django.urls import reverse
        data["next_url"] = reverse(
            "broker_marketplace_page" if broker_setup_required else "dashboard_page"
        )
        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        identifier = str(
            request.data.get("identifier")
            or request.data.get("email")
            or request.data.get("username")
            or ""
        ).strip()
        identity_allowed = allow_auth_attempt(
            request, "jwt-token-login", identifier, limit=10, window=900
        )
        ip_allowed = allow_auth_attempt(
            request, "jwt-token-login-ip", "", limit=30, window=900
        )
        if not identity_allowed or not ip_allowed:
            return Response(
                {"detail": "Too many sign-in attempts. Please wait and try again."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        return super().post(request, *args, **kwargs)


class UserProfileViewSet(viewsets.ModelViewSet):
    """API endpoints for user profiles"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return UserProfile.objects.filter(user=self.request.user)
    
    def get_object(self):
        obj, _ = UserProfile.objects.get_or_create(user=self.request.user)
        return obj
    
    @action(detail=False, methods=['get'])
    def my_profile(self, request):
        profile = self.get_object()
        serializer = UserProfileSerializer(profile, context={'request': request})
        return Response(serializer.data)


class BotSettingsViewSet(viewsets.ModelViewSet):
    """API endpoints for bot settings"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return BotSettings.objects.filter(user=self.request.user)
    
    def get_object(self):
        obj, _ = BotSettings.objects.get_or_create(user=self.request.user)
        return obj
    
    @action(detail=False, methods=['get'])
    def my_settings(self, request):
        settings_obj = self.get_object()
        serializer = BotSettingsSerializer(settings_obj, context={'request': request})
        return Response(serializer.data)


class SubscriptionViewSet(viewsets.ModelViewSet):
    """API endpoints for subscriptions"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Subscription.objects.filter(user=self.request.user)
    
    def get_object(self):
        obj, _ = Subscription.objects.get_or_create(user=self.request.user)
        return obj
    
    @action(detail=False, methods=['get'])
    def my_subscription(self, request):
        subscription = self.get_object()
        serializer = SubscriptionSerializer(subscription, context={'request': request})
        return Response(serializer.data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def browser_api_token(request):
    """Issue a short-lived JWT to an already authenticated browser session.

    The token is returned only in the authenticated API response and is kept
    client-side in memory. Subsequent API requests use Bearer authentication,
    so browser-session API mutations do not depend on Django CSRF cookies.
    """
    from core.broker_onboarding import has_verified_account_email
    profile = UserProfile.objects.filter(user=request.user).first()
    if profile and profile.two_factor_enabled and str(request.session.get("algobot_mfa_verified_user_id", "")) != str(request.user.pk):
        return Response({
            "status": "challenge_required",
            "code": "two_factor_required",
            "message": "Complete a fresh sign-in with your authenticator before requesting browser API credentials.",
            "next_url": "/login/",
        }, status=status.HTTP_403_FORBIDDEN)
    if not has_verified_account_email(request.user):
        return Response({
            'status': 'error',
            'code': 'email_verification_required',
            'message': 'Verify your AlgoBot email before requesting workspace API credentials.',
            'next_url': '/verify-email/',
        }, status=status.HTTP_403_FORBIDDEN)
    refresh = RefreshToken.for_user(request.user)
    from core.broker_onboarding import has_authorized_broker_connection
    from django.urls import reverse
    broker_setup_required = not has_authorized_broker_connection(request.user)
    return Response({
        'access': str(refresh.access_token),
        'expires_in': int(settings.SIMPLE_JWT.get('ACCESS_TOKEN_LIFETIME', timedelta(hours=1)).total_seconds()),
        'broker_setup_required': broker_setup_required,
        'next_url': reverse('broker_marketplace_page'),
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def register(request):
    """Create a local AlgoBot identity with normalized, collision-checked identifiers."""
    username = str(request.data.get('username') or '').strip()
    email = str(request.data.get('email') or '').strip().lower()
    # Passwords are secrets, not identifiers: do not trim valid leading/trailing spaces.
    password = request.data.get('password') or ''
    password_confirm = request.data.get('password_confirm') or ''

    registration_identifier = email or username.lower()
    identity_allowed = allow_auth_attempt(request, 'api-registration-identity', registration_identifier, limit=5, window=3600)
    ip_allowed = allow_auth_attempt(request, 'api-registration-ip', '', limit=10, window=3600)
    if not identity_allowed or not ip_allowed:
        return Response({'status': 'error', 'message': 'Too many registration attempts. Please try again later.'}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    if not username or not email or not password:
        return Response({'status': 'error', 'message': 'Username, email, and password are required'}, status=status.HTTP_400_BAD_REQUEST)
    if password != password_confirm:
        return Response({'status': 'error', 'message': 'Passwords do not match'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        User._meta.get_field('username').clean(username, None)
        validate_email(email)
        validate_password(password, user=User(username=username, email=email))
    except ValidationError as exc:
        return Response({'status': 'error', 'message': ' '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
    if (
        User.objects.filter(username__iexact=username).exists()
        or User.objects.filter(email__iexact=email).exists()
    ):
        return Response(
            {'status': 'error', 'message': 'An account could not be created with those details. If you already have an account, sign in or use account recovery.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        with transaction.atomic():
            user = User.objects.create_user(username=username, email=email, password=password)
            profile, _ = UserProfile.objects.get_or_create(user=user)
            Subscription.objects.get_or_create(user=user)
            BotSettings.objects.get_or_create(user=user)
    except IntegrityError:
        logger.info('user_registration_conflict')
        return Response({'status': 'error', 'message': 'An account could not be created with those details. If you already have an account, sign in or use account recovery.'}, status=status.HTTP_409_CONFLICT)
    except Exception:
        logger.exception('user_registration_failed')
        return Response({'status': 'error', 'message': 'Registration could not be completed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    from core.browser_auth import _send_verification
    email_sent = _send_verification(request, user, profile)
    logger.info('user_registered', extra={'user_id': user.pk})
    return Response({
        'status': 'success',
        'message': 'User registered successfully' if email_sent else 'User registered; verification email delivery is temporarily unavailable.',
        'user_id': user.id,
        'username': user.username,
        'email': user.email,
        'email_verification_sent': email_sent,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_view(request):
    """Authenticate by username or a unique email address."""
    identifier = str(request.data.get('identifier') or request.data.get('username') or request.data.get('email') or '').strip()
    password = request.data.get('password') or ''
    identifier_allowed = allow_auth_attempt(request, 'api-password-login', identifier, limit=10, window=900)
    ip_allowed = allow_auth_attempt(request, 'api-password-login-ip', '', limit=30, window=900)
    if not identifier_allowed or not ip_allowed:
        return Response({'status': 'error', 'message': 'Too many sign-in attempts. Please wait and try again.'}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    if not identifier or not password:
        return Response({'status': 'error', 'message': 'Username/email and password are required'}, status=status.HTTP_400_BAD_REQUEST)

    from django.contrib.auth import authenticate
    user = None
    if '@' in identifier:
        matches = User.objects.filter(email__iexact=identifier)
        if matches.count() == 1:
            candidate = matches.first()
            user = authenticate(request, username=candidate.get_username(), password=password)
    else:
        user = authenticate(request, username=identifier, password=password)
        if user is None:
            matches = User.objects.filter(username__iexact=identifier)
            if matches.count() == 1:
                candidate = matches.first()
                user = authenticate(request, username=candidate.get_username(), password=password)

    if not user:
        # Use the same public response for unknown users and bad passwords.
        return Response({'status': 'error', 'message': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

    profile = UserProfile.objects.filter(user=user).first()
    if not profile or not profile.email_verified:
        return Response(
            {'status': 'error', 'message': 'Please verify your email before signing in.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    if profile.two_factor_enabled:
        from core.services.two_factor_service import verify_user_code
        two_factor_code = request.data.get("two_factor_code") or ""
        if not two_factor_code:
            return Response({
                "status": "challenge_required",
                "code": "two_factor_required",
                "message": "A valid authenticator or recovery code is required to complete sign-in.",
            }, status=status.HTTP_403_FORBIDDEN)
        if not verify_user_code(profile, two_factor_code, consume_recovery=True):
            return Response({
                "status": "error",
                "code": "two_factor_invalid",
                "message": "The authenticator or recovery code is invalid.",
            }, status=status.HTTP_401_UNAUTHORIZED)

    UserProfile.objects.update_or_create(user=user, defaults={'last_login_at': timezone.now()})
    refresh = RefreshToken.for_user(user)
    from core.broker_onboarding import has_authorized_broker_connection
    from django.urls import reverse
    broker_setup_required = not has_authorized_broker_connection(user)
    logger.info('user_login_succeeded', extra={'user_id': user.pk})
    return Response({
        'status': 'success',
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': {'id': user.id, 'username': user.username, 'email': user.email},
        'broker_setup_required': broker_setup_required,
        'next_url': reverse('broker_marketplace_page'),
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def logout_view(request):
    """Revoke the caller's refresh token without allowing cross-user revocation."""
    raw_refresh = request.data.get('refresh')
    if not raw_refresh:
        return Response({'status': 'error', 'message': 'Refresh token is required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        token = RefreshToken(raw_refresh)
    except TokenError:
        return Response({'status': 'error', 'message': 'Refresh token is invalid or already revoked.'}, status=status.HTTP_400_BAD_REQUEST)
    if str(token.get('user_id')) != str(request.user.pk):
        return Response({'status': 'error', 'message': 'Refresh token does not belong to the authenticated user.'}, status=status.HTTP_403_FORBIDDEN)
    token.blacklist()
    return Response({'status': 'success', 'message': 'Refresh token revoked.'}, status=status.HTTP_205_RESET_CONTENT)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def change_password(request):
    """Change user password endpoint"""
    try:
        # Passwords may legitimately contain whitespace; never normalize them.
        old_password = request.data.get('old_password', '')
        new_password = request.data.get('new_password', '')
        new_password_confirm = request.data.get('new_password_confirm', '')
        
        if not old_password or not new_password:
            return Response({
                'status': 'error',
                'message': 'Old and new passwords are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if new_password != new_password_confirm:
            return Response({
                'status': 'error',
                'message': 'New passwords do not match'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user
        try:
            validate_password(new_password, user=user)
        except ValidationError as exc:
            return Response({
                'status': 'error',
                'message': ' '.join(exc.messages)
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not user.check_password(old_password):
            return Response({
                'status': 'error',
                'message': 'Current password is incorrect'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        with transaction.atomic():
            user.set_password(new_password)
            user.save(update_fields=['password'])
            # Revoke outstanding refresh tokens immediately after credential change.
            from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
            for outstanding in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=outstanding)

        logger.info('user_password_changed', extra={'user_id': user.pk})
        
        return Response({
            'status': 'success',
            'message': 'Password changed successfully'
        }, status=status.HTTP_200_OK)
    
    except Exception:
        logger.exception('user_password_change_failed')
        return Response({
            'status': 'error',
            'message': 'Password change failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
