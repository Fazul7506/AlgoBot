"""Resource-specific websocket consumers backed by the canonical event bus."""
from __future__ import annotations

from channels.db import database_sync_to_async
from django.utils import timezone

from .broker_events import BrokerEventConsumer


class PortfolioBrokerEventConsumer(BrokerEventConsumer):
    resource = "portfolio"

    async def connect(self):
        await super().connect()
        await self.send_json({"type": "portfolio.snapshot", **await self.portfolio_snapshot()})

    @database_sync_to_async
    def portfolio_snapshot(self):
        from apps.brokers.models import BrokerAccount

        account = (
            BrokerAccount.objects.filter(
                user=self.scope["user"], status="active", broker__status="active"
            )
            .select_related("broker")
            .order_by("-is_preferred", "-id")
            .first()
        )
        if not account:
            return {"status": "empty", "balance": None, "equity": None, "unrealized_pnl": None}
        realtime = dict((account.credentials or {}).get("realtime") or {})
        return {
            "status": "ready",
            "account_id": account.account_id,
            "broker": account.broker.broker_type,
            "balance": str(account.balance),
            "equity": str(account.equity),
            "currency": account.currency,
            "unrealized_pnl": realtime.get("unrealized_pnl"),
            "last_synced_at": account.last_synced_at.timestamp() if account.last_synced_at else None,
            "timestamp": timezone.now().timestamp(),
        }


class NotificationBrokerEventConsumer(BrokerEventConsumer):
    resource = "notifications"

    async def connect(self):
        await super().connect()
        await self.send_json({"type": "notification.snapshot", "notifications": await self.latest_notifications()})

    @database_sync_to_async
    def latest_notifications(self):
        from apps.notifications.models import Notification

        rows = Notification.objects.filter(user=self.scope["user"]).order_by("-created_at")[:20]
        return [
            {
                "id": row.pk,
                "type": "notification",
                "severity": row.priority,
                "title": row.title,
                "message": row.message,
                "timestamp": row.created_at.timestamp(),
                "read": row.read_at is not None,
            }
            for row in rows
        ]
