import logging
logger = logging.getLogger(__name__)
class EventBus:
    def publish(self, event, payload):
        logger.info("market_data.event", extra={"event": event, "payload": payload})
        return {"event": event, "payload": payload}
event_bus = EventBus()
