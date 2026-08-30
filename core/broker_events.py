"""Authenticated websocket fanout for the canonical broker event bus.

The broker worker is the sole source of live account state. Browser consumers
subscribe to the per-user Channels group and never open broker WebSockets or
poll broker endpoints themselves.
"""
from __future__ import annotations

from django.utils import timezone
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class BrokerEventConsumer(AsyncJsonWebsocketConsumer):
    """Forward canonical broker events to one authenticated AlgoBot user."""

    resource = "broker"

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.group_name = f"algobot-user-{user.pk}-broker"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
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

    async def broker_event(self, event):
        """Channels group handler for BrokerRealtimeSync events."""
        await self.send_json({
            "type": event.get("event_type", "broker.event"),
            "payload": event.get("payload") or {},
            "source": "broker",
            "timestamp": timezone.now().timestamp(),
        })
