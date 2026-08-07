from .models import Notification
class NotificationRepository:
    def unread(self,user): return Notification.objects.filter(user=user,read_at__isnull=True)
