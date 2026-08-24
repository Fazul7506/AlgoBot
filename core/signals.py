"""Signal handlers for core models."""
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import UserProfile, Subscription, BotSettings


@receiver(post_save, sender=get_user_model())
def ensure_user_related_models(sender, instance, created, **kwargs):
    """Create related objects when user is created"""
    if not created:
        return

    try:
        UserProfile.objects.get_or_create(user=instance)
        Subscription.objects.get_or_create(user=instance)
        BotSettings.objects.get_or_create(user=instance)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating related objects for user {instance.username}: {e}")


def canonical_deriv_account(user):
    """Get preferred Deriv account for user"""
    from apps.brokers.models import BrokerAccount
    account = BrokerAccount.objects.filter(
        user=user,
        broker__broker_type="deriv",
        is_preferred=True,
    ).select_related("broker").first()
    if account is None:
        raise BrokerAccount.DoesNotExist
    return account


User = get_user_model()
if not hasattr(User, "deriv_account"):
    User.add_to_class("deriv_account", property(canonical_deriv_account))
