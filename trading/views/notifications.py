from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from trading.models.notifications import Notification
from trading.services.notification_service import NotificationService


class NotificationViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def _get_profile(self, user):
        profile = getattr(user, 'trading_profile', None)
        if profile is None:
            profile = getattr(user, 'bot_settings', None)
        return profile

    @action(detail=False, methods=['post'])
    def send(self, request):
        alert_type = request.data.get('alert_type')
        channels = request.data.get('channels') or ['email', 'push']
        details = request.data.get('details') or {}
        if isinstance(channels, str):
            channels = [channels]
        if not alert_type:
            return Response({'status': 'error', 'message': 'alert_type is required'}, status=status.HTTP_400_BAD_REQUEST)
        result = NotificationService(user=request.user).send(alert_type, details=details, channels=channels)
        return Response({'status': 'success', 'data': result}, status=status.HTTP_200_OK)

    def list(self, request):
        limit = int(request.query_params.get('limit', 20))
        notifications = Notification.objects.filter(user=request.user).order_by('-created_at')[:limit]
        return Response({'status': 'success', 'count': notifications.count(), 'data': [
            {
                'id': item.id,
                'alert_type': item.alert_type,
                'message': item.message,
                'channels': item.channels,
                'delivered_channels': item.delivered_channels,
                'status': item.status,
                'is_read': item.is_read,
                'created_at': item.created_at.isoformat(),
            }
            for item in notifications
        ]}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def preferences(self, request):
        profile = self._get_profile(request.user)
        if profile is None:
            return Response({'status': 'error', 'message': 'Notification profile not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'status': 'success', 'data': {
            'email_notifications_enabled': profile.email_notifications_enabled,
            'telegram_notifications_enabled': profile.telegram_notifications_enabled,
            'telegram_chat_id': profile.telegram_chat_id,
            'telegram_username': getattr(profile, 'telegram_username', ''),
            'brevo_sender_email': getattr(profile, 'brevo_sender_email', ''),
        }}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def update_preferences(self, request):
        profile = self._get_profile(request.user)
        if profile is None:
            return Response({'status': 'error', 'message': 'Notification profile not found'}, status=status.HTTP_404_NOT_FOUND)
        profile.email_notifications_enabled = bool(request.data.get('email_notifications_enabled', profile.email_notifications_enabled))
        profile.telegram_notifications_enabled = bool(request.data.get('telegram_notifications_enabled', profile.telegram_notifications_enabled))
        profile.telegram_chat_id = request.data.get('telegram_chat_id', profile.telegram_chat_id) or ''
        profile.telegram_username = request.data.get('telegram_username', getattr(profile, 'telegram_username', '')) or ''
        profile.brevo_api_key = request.data.get('brevo_api_key', getattr(profile, 'brevo_api_key', '')) or ''
        profile.brevo_sender_email = request.data.get('brevo_sender_email', getattr(profile, 'brevo_sender_email', '')) or ''
        profile.save()
        return Response({'status': 'success', 'data': {
            'email_notifications_enabled': profile.email_notifications_enabled,
            'telegram_notifications_enabled': profile.telegram_notifications_enabled,
            'telegram_chat_id': profile.telegram_chat_id,
            'telegram_username': getattr(profile, 'telegram_username', ''),
            'brevo_sender_email': getattr(profile, 'brevo_sender_email', ''),
        }}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def connect_telegram(self, request):
        profile = self._get_profile(request.user)
        if profile is None:
            return Response({'status': 'error', 'message': 'Notification profile not found'}, status=status.HTTP_404_NOT_FOUND)

        telegram_chat_id = request.data.get('telegram_chat_id')
        telegram_username = request.data.get('telegram_username')
        if not telegram_chat_id:
            return Response({'status': 'error', 'message': 'telegram_chat_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        profile.telegram_chat_id = telegram_chat_id
        if telegram_username:
            profile.telegram_username = telegram_username
        profile.telegram_notifications_enabled = True
        profile.save()
        return Response({'status': 'success', 'data': {
            'telegram_chat_id': profile.telegram_chat_id,
            'telegram_username': getattr(profile, 'telegram_username', ''),
            'telegram_notifications_enabled': profile.telegram_notifications_enabled,
        }}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def disconnect_telegram(self, request):
        profile = self._get_profile(request.user)
        if profile is None:
            return Response({'status': 'error', 'message': 'Notification profile not found'}, status=status.HTTP_404_NOT_FOUND)

        profile.telegram_chat_id = ''
        profile.telegram_username = ''
        profile.telegram_notifications_enabled = False
        profile.save()
        return Response({'status': 'success', 'data': {
            'telegram_chat_id': profile.telegram_chat_id,
            'telegram_username': profile.telegram_username,
            'telegram_notifications_enabled': profile.telegram_notifications_enabled,
        }}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def mark_read(self, request):
        notification_id = request.data.get('notification_id')
        if notification_id is None:
            return Response({'status': 'error', 'message': 'notification_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        notification = Notification.objects.filter(user=request.user, id=notification_id).first()
        if not notification:
            return Response({'status': 'error', 'message': 'Notification not found'}, status=status.HTTP_404_NOT_FOUND)
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response({'status': 'success', 'data': {'id': notification.id, 'is_read': notification.is_read}}, status=status.HTTP_200_OK)
