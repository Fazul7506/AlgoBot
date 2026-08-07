from .models import Broadcast, Notification
from .services import BroadcastService, DeliveryService, DigestService
def dispatch_notification(notification_id): return DeliveryService().deliver(Notification.objects.get(id=notification_id)).status
def schedule_broadcast(broadcast_id): return BroadcastService().send(Broadcast.objects.get(id=broadcast_id))
def generate_digest(user_id, frequency="daily"):
    from django.contrib.auth import get_user_model
    return DigestService().generate(get_user_model().objects.get(id=user_id), frequency)
