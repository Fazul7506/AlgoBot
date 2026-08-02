import logging
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import secrets

from core.models import UserProfile, Subscription, BotSettings, PasswordResetToken
from core.serializers import (
    UserSerializer, UserProfileSerializer, RegisterSerializer,
    LoginSerializer, PasswordResetSerializer, PasswordResetConfirmSerializer,
    ChangePasswordSerializer, SubscriptionSerializer, BotSettingsSerializer
)

logger = logging.getLogger(__name__)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['email'] = user.email
        return token


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def register(request):
    """User registration endpoint"""
    try:
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            logger.info(f"New user registered: {user.username}")
            
            return Response({
                'status': 'success',
                'message': 'User registered successfully',
                'user_id': user.id,
                'username': user.username,
                'email': user.email
            }, status=status.HTTP_201_CREATED)
        return Response({
            'status': 'error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Registration error: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Registration failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login(request):
    """JWT login endpoint"""
    try:
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # Update last login
            profile = user.trading_profile
            profile.last_login_at = timezone.now()
            profile.save()
            
            # Generate JWT token
            from rest_framework_simplejwt.tokens import RefreshToken
            refresh = RefreshToken.for_user(user)
            
            logger.info(f"User login: {user.username}")
            
            return Response({
                'status': 'success',
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': UserSerializer(user).data
            }, status=status.HTTP_200_OK)
        return Response({
            'status': 'error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Login error: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Login failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def logout(request):
    """Logout endpoint (token invalidation handled client-side in JWT)"""
    logger.info(f"User logout: {request.user.username}")
    return Response({
        'status': 'success',
        'message': 'Logged out successfully'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def password_reset_request(request):
    """Request password reset token"""
    try:
        serializer = PasswordResetSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            user = User.objects.get(email=email)
            
            # Generate reset token
            token = secrets.token_urlsafe(64)
            expires_at = timezone.now() + timedelta(hours=24)
            
            PasswordResetToken.objects.create(
                user=user,
                token=token,
                expires_at=expires_at
            )
            
            # Send email (in production, use celery for async)
            reset_url = request.build_absolute_uri(f'/reset-password/{token}')
            from core.tasks import send_email
            send_email(
                subject='Password Reset Request',
                message=f'Click here to reset your password: {reset_url}',
                recipient_list=[email],
                from_email=settings.DEFAULT_FROM_EMAIL,
            )
            
            logger.info(f"Password reset requested for: {email}")
            
            return Response({
                'status': 'success',
                'message': 'Password reset email sent'
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Password reset request error: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Password reset failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def password_reset_confirm(request):
    """Confirm password reset with token"""
    try:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            token_str = serializer.validated_data['token']
            new_password = serializer.validated_data['new_password']
            
            # Validate token
            reset_token = PasswordResetToken.objects.get(token=token_str)
            if not reset_token.is_valid():
                return Response({
                    'status': 'error',
                    'message': 'Invalid or expired token'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Update password
            user = reset_token.user
            user.set_password(new_password)
            user.save()
            
            # Mark token as used
            reset_token.used = True
            reset_token.used_at = timezone.now()
            reset_token.save()
            
            logger.info(f"Password reset completed for: {user.username}")
            
            return Response({
                'status': 'success',
                'message': 'Password reset successfully'
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Password reset confirm error: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Password reset failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def change_password(request):
    """Change password for authenticated user"""
    try:
        user = request.user
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            if not user.check_password(serializer.validated_data['old_password']):
                return Response({
                    'status': 'error',
                    'message': 'Old password is incorrect'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            
            logger.info(f"Password changed for: {user.username}")
            
            return Response({
                'status': 'success',
                'message': 'Password changed successfully'
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Change password error: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Password change failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserProfileViewSet(viewsets.ModelViewSet):
    """User profile management"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserProfileSerializer
    
    def get_queryset(self):
        return UserProfile.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get', 'put'])
    def my_profile(self, request):
        """Get or update current user's profile"""
        profile = request.user.trading_profile
        if request.method == 'PUT':
            serializer = self.get_serializer(profile, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                logger.info(f"Profile updated for: {request.user.username}")
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = self.get_serializer(profile)
        return Response(serializer.data)


class BotSettingsViewSet(viewsets.ModelViewSet):
    """Bot settings management"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BotSettingsSerializer
    
    def get_queryset(self):
        return BotSettings.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get', 'put'])
    def my_settings(self, request):
        """Get or update current user's bot settings"""
        settings_obj = request.user.bot_settings
        if request.method == 'PUT':
            serializer = self.get_serializer(settings_obj, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                logger.info(f"Bot settings updated for: {request.user.username}")
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = self.get_serializer(settings_obj)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def start_bot(self, request):
        """Start bot trading"""
        settings_obj = request.user.bot_settings
        settings_obj.is_enabled = True
        settings_obj.status = 'RUNNING'
        settings_obj.save()
        logger.info(f"Bot started for: {request.user.username}")
        return Response({'status': 'success', 'message': 'Bot started'})
    
    @action(detail=False, methods=['post'])
    def stop_bot(self, request):
        """Stop bot trading"""
        settings_obj = request.user.bot_settings
        settings_obj.is_enabled = False
        settings_obj.status = 'IDLE'
        settings_obj.save()
        logger.info(f"Bot stopped for: {request.user.username}")
        return Response({'status': 'success', 'message': 'Bot stopped'})


class SubscriptionViewSet(viewsets.ModelViewSet):
    """Subscription management (read-only for users)"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SubscriptionSerializer
    
    def get_queryset(self):
        return Subscription.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def my_subscription(self, request):
        """Get current user's subscription"""
        subscription = request.user.subscription
        serializer = self.get_serializer(subscription)
        return Response(serializer.data)
