"""Portfolio websocket event helpers."""


class PortfolioSocketService:
    def build_event(self, event_type, payload=None):
        return {
            "event": event_type,
            "payload": payload or {},
            "status": "ok",
        }
