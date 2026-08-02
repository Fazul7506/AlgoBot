from .constants import WEBSOCKET_EVENTS
def broadcast_ai_event(event, payload):
    if event not in WEBSOCKET_EVENTS: raise ValueError('Unsupported AI websocket event')
    return {'event':event,'payload':payload}
