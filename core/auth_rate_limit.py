"""Small fail-closed rate limiter for browser authentication endpoints."""
import hashlib
import logging

from django.core.cache import cache

logger = logging.getLogger("account_auth")


def allow_auth_attempt(request, action, identity="", *, limit=5, window=3600):
    """Allow a bounded number of attempts per client IP and normalized identity.

    Only a one-way digest is stored in cache; emails and usernames are never
    written to cache keys in plaintext. If the configured cache is unavailable,
    deny sensitive attempts rather than silently disabling abuse protection.
    """
    remote_ip = str(request.META.get("REMOTE_ADDR") or "unknown")
    normalized = str(identity or "").strip().lower()
    # Identity counters are global across source IPs; blank-identity calls are
    # IP counters. Callers apply both limits separately so distributed clients
    # cannot evade an identity cap and one account cannot evade an IP cap.
    material = (
        f"{action}|identity|{normalized}" if normalized
        else f"{action}|ip|{remote_ip}"
    ).encode("utf-8")
    key = "algobot:auth-rate:" + hashlib.sha256(material).hexdigest()
    try:
        if cache.add(key, 1, timeout=window):
            return True
        try:
            attempts = cache.incr(key)
        except ValueError:
            if cache.add(key, 1, timeout=window):
                return True
            attempts = cache.incr(key)
        return attempts <= limit
    except Exception:
        logger.warning("auth_rate_limit_backend_unavailable", extra={"action": action})
        return False
