from .constants import WEBSOCKET_EVENTS

def monitoring_group_name():
    return "monitoring.events"

def serialize_event(event_type, payload):
    if event_type not in WEBSOCKET_EVENTS:
        raise ValueError(f"Unsupported monitoring websocket event: {event_type}")
    return {"type": event_type, "payload": payload}
