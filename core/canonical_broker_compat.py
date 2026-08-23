"""Temporary compatibility attributes for legacy browser views.

No broker model is declared here. The canonical state is apps.brokers.models.BrokerAccount.
"""
from django.contrib.auth.models import User


def install_user_deriv_account_property():
    if hasattr(User, "deriv_account"):
        return

    def _deriv_account(user):
        from apps.brokers.models import BrokerAccount
        account = BrokerAccount.objects.filter(
            user=user,
            broker__broker_type="deriv",
            is_preferred=True,
        ).select_related("broker").first()
        if account is None:
            raise BrokerAccount.DoesNotExist
        return account

    User.add_to_class("deriv_account", property(_deriv_account))
