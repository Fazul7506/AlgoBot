from .constants import WEBSOCKET_EVENTS
def automation_group(user_id): return f"automation:{user_id}"
def event_payload(event, **data): return {"type":"automation.event","event":event,"data":data}
