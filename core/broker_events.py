"""Authenticated websocket fanout for the canonical broker event bus.

The broker worker is the sole source of live account state. Browser consumers
subscribe to the per-user Channels group and never open broker WebSockets or
poll broker endpoints themselves.
"""
from __future__ import annotations

from django.utils import timezone
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .account_context import get_active_account_for_session


def account_event_matches_active_account(payload, active_account_pk):
    """Keep account-scoped events inside the account selected by the HTTP session."""
    event_account_id = payload.get("account_id") if isinstance(payload, dict) else None
    if event_account_id is None:
        return True
    return active_account_pk is not None and str(event_account_id) == str(active_account_pk)


class BrokerEventConsumer(AsyncJsonWebsocketConsumer):
    """Forward canonical broker events to one authenticated AlgoBot user."""

    resource = "broker"

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            self._broker_connection_accepted = False
            await self.close(code=4401)
            return
        self.active_account_pk = await self.selected_account_pk()
        self.group_name = f"algobot-user-{user.pk}-broker"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        self._broker_connection_accepted = True
        await self.send_json({
            "type": "connection.ready",
            "resource": self.resource,
            "source": "canonical_broker_event_bus",
            "status": "connected",
            "timestamp": timezone.now().timestamp(),
        })

    async def disconnect(self, close_code):
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        action = str(content.get("action") or "").lower()
        if action == "ping":
            await self.send_json({"type": "pong", "timestamp": timezone.now().timestamp()})
            return
        if action in {"subscribe", "unsubscribe"}:
            await self.send_json({
                "type": "subscription",
                "status": "subscribed" if action == "subscribe" else "unsubscribed",
                "source": "canonical_broker_event_bus",
            })
            return
        await self.send_json({
            "type": "error",
            "error": {
                "code": "UNSUPPORTED_ACTION",
                "message": "Live broker state is server-authoritative; use explicit trading APIs for actions.",
            },
        })

    @database_sync_to_async
    def selected_account_pk(self):
        account = get_active_account_for_session(self.scope.get("user"), self.scope.get("session"))
        return account.pk if account else None

    async def broker_event(self, event):
        """Forward only the account-scoped events selected in this HTTP session."""
        payload = event.get("payload") or {}
        if not account_event_matches_active_account(payload, getattr(self, "active_account_pk", None)):
            return
        await self.send_json({
            "type": event.get("event_type", "broker.event"),
            "payload": payload,
            "source": "broker",
            "timestamp": timezone.now().timestamp(),
        })
