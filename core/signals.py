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


def canonical_deriv_account(user):
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
