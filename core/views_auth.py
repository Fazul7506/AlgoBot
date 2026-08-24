"""API views for authentication and user management."""
import logging
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import secrets

from core.models import UserProfile, Subscription, BotSettings, PasswordResetToken

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
        from rest_framework import serializers
        
        class UserProfileSerializer(serializers.ModelSerializer):
            class Meta:
                model = UserProfile
                fields = '__all__'
        
        serializer = UserProfileSerializer(profile)
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
        from rest_framework import serializers
        
        class BotSettingsSerializer(serializers.ModelSerializer):
            class Meta:
                model = BotSettings
                fields = '__all__'
        
        serializer = BotSettingsSerializer(settings_obj)
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
        from rest_framework import serializers
        
        class SubscriptionSerializer(serializers.ModelSerializer):
            class Meta:
                model = Subscription
                fields = '__all__'
        
        serializer = SubscriptionSerializer(subscription)
        return Response(serializer.data)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def register(request):
    """User registration endpoint"""
    try:
        username = request.data.get('username', '').strip()
        email = request.data.get('email', '').strip()
        password = request.data.get('password', '').strip()
        password_confirm = request.data.get('password_confirm', '').strip()
        
        # Validation
        if not username or not email or not password:
            return Response({
                'status': 'error',
                'message': 'Username, email, and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if password != password_confirm:
            return Response({
                'status': 'error',
                'message': 'Passwords do not match'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if len(password) < 8:
            return Response({
                'status': 'error',
                'message': 'Password must be at least 8 characters'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if User.objects.filter(username=username).exists():
            return Response({
                'status': 'error',
                'message': 'Username already exists'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if User.objects.filter(email=email).exists():
            return Response({
                'status': 'error',
                'message': 'Email already registered'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create user
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )
        
        # Create related objects
        UserProfile.objects.get_or_create(user=user)
        Subscription.objects.get_or_create(user=user)
        BotSettings.objects.get_or_create(user=user)
        
        logger.info(f"New user registered: {username}")
        
        return Response({
            'status': 'success',
            'message': 'User registered successfully',
            'user_id': user.id,
            'username': user.username,
            'email': user.email
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        logger.error(f"Registration error: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Registration failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_view(request):
    """JWT login endpoint"""
    try:
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '').strip()
        
        if not username or not password:
            return Response({
                'status': 'error',
                'message': 'Username and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        from django.contrib.auth import authenticate
        user = authenticate(username=username, password=password)
        
        if not user:
            return Response({
                'status': 'error',
                'message': 'Invalid credentials'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Update last login
        try:
            profile = user.trading_profile
            profile.last_login_at = timezone.now()
            profile.save(update_fields=['last_login_at'])
        except:
            pass
        
        # Generate JWT token
        refresh = RefreshToken.for_user(user)
        
        logger.info(f"User login: {username}")
        
        return Response({
            'status': 'success',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Login error: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Login failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def change_password(request):
    """Change user password endpoint"""
    try:
        old_password = request.data.get('old_password', '').strip()
        new_password = request.data.get('new_password', '').strip()
        new_password_confirm = request.data.get('new_password_confirm', '').strip()
        
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
        
        if len(new_password) < 8:
            return Response({
                'status': 'error',
                'message': 'Password must be at least 8 characters'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user
        if not user.check_password(old_password):
            return Response({
                'status': 'error',
                'message': 'Current password is incorrect'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        user.set_password(new_password)
        user.save()
        
        logger.info(f"Password changed: {user.username}")
        
        return Response({
            'status': 'success',
            'message': 'Password changed successfully'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Change password error: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Password change failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
