class DeterministicEventManager:
    def __init__(self): self._seen=set()
    def emit_once(self, event, key):
        token=(event, tuple(sorted(key.items())) if isinstance(key,dict) else key)
        if token in self._seen: return False
        self._seen.add(token); return True
