"""Bounded rate limiting with a local emergency fallback when shared cache is down."""
import hashlib
import logging
from threading import Lock

from django.core.cache import cache
from django.core.cache.backends.locmem import LocMemCache

logger = logging.getLogger("account_auth")
_fallback_cache = LocMemCache("algobot-auth-rate-limit-fallback", {})
_fallback_lock = Lock()


def allow_auth_attempt(request, action, identity="", *, limit=5, window=3600):
    """Allow bounded attempts per normalized identity or per source IP.

    Callers apply both counters for sensitive operations. Identity counters are
    global across IPs; blank-identity counters are scoped to the source IP.
    Only a one-way digest is stored in cache keys. If the shared cache is
    unavailable, use a bounded per-process fallback so authentication remains
    usable without disabling throttling entirely. The fallback is temporary
    and less strong than shared storage; alerting still makes the outage visible.
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
        logger.error(
            "auth_rate_limit_backend_unavailable_using_process_fallback",
            extra={"action": action},
        )
        # Lock the local counter operations to avoid races among requests handled
        # by this process. Shared-cache recovery automatically restores the
        # stronger cross-worker counters on the next request.
        try:
            with _fallback_lock:
                if _fallback_cache.add(key, 1, timeout=window):
                    return True
                try:
                    attempts = _fallback_cache.incr(key)
                except ValueError:
                    if _fallback_cache.add(key, 1, timeout=window):
                        return True
                    attempts = _fallback_cache.incr(key)
                return attempts <= limit
        except Exception:
            logger.critical("auth_rate_limit_fallback_unavailable", extra={"action": action})
            return False
