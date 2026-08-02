import logging
from django.conf import settings
from trading.models.copy import CopyFollow, CopyTrade
from trading.models import Trade
from django.utils import timezone

logger = logging.getLogger(__name__)


class CopyService:
    """Service to manage follow relationships and execute copy trades."""

    def __init__(self):
        pass

    def follow(self, leader_user, follower_user, allocation_type='PERCENT', allocation_value=10.0):
        obj, created = CopyFollow.objects.update_or_create(
            leader=leader_user, follower=follower_user,
            defaults={'allocation_type': allocation_type, 'allocation_value': allocation_value, 'is_active': True}
        )
        return obj

    def unfollow(self, leader_user, follower_user):
        CopyFollow.objects.filter(leader=leader_user, follower=follower_user).update(is_active=False)

    def handle_leader_trade(self, leader_trade: Trade):
        """When a leader opens a trade, replicate it to active followers according to allocation."""
        followers = CopyFollow.objects.filter(leader=leader_trade.user, is_active=True)
        created_records = []

        for f in followers:
            try:
                # Determine allocation amount
                if f.allocation_type == 'PERCENT':
                    # Placeholder: get follower's account equity; use profile paper_balance if exists
                    equity = getattr(getattr(f.follower, 'bot_settings', None), 'paper_balance', 1000.0)
                    amount = (f.allocation_value / 100.0) * equity
                else:
                    amount = f.allocation_value

                # Create a CopyTrade record; actual trade execution should be delegated
                ct = CopyTrade.objects.create(
                    leader_trade_id=str(leader_trade.id),
                    follower=f.follower,
                    amount=amount,
                    status='PENDING'
                )
                created_records.append(ct)

                # Optionally, kick off trade execution (not implemented here).

            except Exception:
                logger.exception('Failed to create copy trade for follower %s', getattr(f.follower, 'username', None))

        return created_records
