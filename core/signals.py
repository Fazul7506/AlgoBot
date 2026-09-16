"""Signal handlers for core models."""
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import UserProfile, Subscription, BotSettings


@receiver(post_save, sender=get_user_model())
def ensure_user_related_models(sender, instance, created, **kwargs):
    """Create related objects when user is created."""
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
    """Return the authenticated user's active Deriv account without legacy preference state."""
    from apps.brokers.models import BrokerAccount
    account = (
        BrokerAccount.objects.filter(
            user=user,
            broker__broker_type="deriv",
            status="active",
            broker__status="active",
            connections__status="connected",
        )
        .select_related("broker")
        .distinct()
        .order_by("-last_synced_at", "-id")
        .first()
    )
    if account is None:
        raise BrokerAccount.DoesNotExist
    return account


User = get_user_model()
if not hasattr(User, "deriv_account"):
    User.add_to_class("deriv_account", property(canonical_deriv_account))
