from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import UserProfile, Subscription, BotSettings


@receiver(post_save, sender=get_user_model())
def ensure_user_related_models(sender, instance, created, **kwargs):
    if not created:
        return

    UserProfile.objects.get_or_create(user=instance)
    Subscription.objects.get_or_create(user=instance)
    BotSettings.objects.get_or_create(user=instance)
