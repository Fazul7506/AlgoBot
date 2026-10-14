"""API views for authentication and user management."""
import logging
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.contrib.auth.password_validation import validate_password
from django.conf import settings
from datetime import timedelta
import secrets

from core.models import UserProfile, Subscription, BotSettings, PasswordResetToken
from core.serializers import UserProfileSerializer, SubscriptionSerializer, BotSettingsSerializer

logger = logging.getLogger(__name__)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    identifier = serializers.CharField(required=False, write_only=True)
    email = serializers.EmailField(required=False, write_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep the legacy username field while allowing email/identifier clients.
        self.fields[self.username_field].required = False

    def validate(self, attrs):
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
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['email'] = user.email
        return token


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


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
    refresh = RefreshToken.for_user(request.user)
    return Response({
        'access': str(refresh.access_token),
        'expires_in': int(settings.SIMPLE_JWT.get('ACCESS_TOKEN_LIFETIME', timedelta(hours=1)).total_seconds()),
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
    if User.objects.filter(username__iexact=username).exists():
        return Response({'status': 'error', 'message': 'Username already exists'}, status=status.HTTP_400_BAD_REQUEST)
    if User.objects.filter(email__iexact=email).exists():
        return Response({'status': 'error', 'message': 'Email already registered'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            user = User.objects.create_user(username=username, email=email, password=password)
            profile, _ = UserProfile.objects.get_or_create(user=user)
            Subscription.objects.get_or_create(user=user)
            BotSettings.objects.get_or_create(user=user)
    except IntegrityError:
        logger.info('user_registration_conflict')
        return Response({'status': 'error', 'message': 'Username or email already registered'}, status=status.HTTP_409_CONFLICT)
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

    UserProfile.objects.update_or_create(user=user, defaults={'last_login_at': timezone.now()})
    refresh = RefreshToken.for_user(user)
    logger.info('user_login_succeeded', extra={'user_id': user.pk})
    return Response({
        'status': 'success',
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': {'id': user.id, 'username': user.username, 'email': user.email},
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
