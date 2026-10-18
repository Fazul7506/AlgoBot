import hashlib
import logging
import time
import uuid

from django.core.cache import cache
from django.core.cache.backends.locmem import LocMemCache
from django.http import JsonResponse
from django.utils import timezone
from django_redis.exceptions import ConnectionInterrupted
from redis.exceptions import RedisError

from .models import APIKey, APIUsageEvent, RateLimitEvent

logger = logging.getLogger(__name__)

# A Redis quota/availability incident must not turn every developer API request
# into a 500. This emergency limiter is intentionally process-local: it is a
# bounded degraded mode, not a replacement for shared Redis enforcement.
_fallback_rate_limit_cache = LocMemCache("algobot-developer-rate-limit-fallback", {})
_REDIS_FAILURE_COOLDOWN_SECONDS = 30.0
_redis_unavailable_until = 0.0


def _increment_rate_counter(backend, key, window):
    """Increment an existing Redis counter directly; expire only a new key."""
    # django-redis's cache.incr() checks key existence before issuing INCR.
    # Calling the underlying client avoids that extra EXISTS command on every
    # request. Keep the cache key transformation so prefixes/versions still
    # match Django's cache API.
    from django.conf import settings

    if backend is cache and getattr(settings, "USE_REDIS", False):
        from django_redis import get_redis_connection

        redis_client = get_redis_connection("default")
        redis_key = backend.make_key(key)
        count = redis_client.incr(redis_key)
        if count == 1:
            redis_client.expire(redis_key, max(1, int(window)))
        return count

    # LocMemCache and test doubles use Django's backend API. A missing key
    # raises ValueError; add() gives it a TTL and handles first-request races.
    try:
        return backend.incr(key)
    except (ValueError, TypeError):
        if backend.add(key, 1, timeout=window):
            return 1
        try:
            return backend.incr(key)
        except (ValueError, TypeError):
            # The key may expire between the retry and increment. Re-create it
            # with the requested TTL, retrying once if another request wins.
            if backend.add(key, 1, timeout=window):
                return 1
            return backend.incr(key)


def _next_rate_limit_count(key, window):
    """Use shared Redis normally and a local counter during Redis failures."""
    global _redis_unavailable_until

    now = time.monotonic()
    if now < _redis_unavailable_until:
        return _increment_rate_counter(_fallback_rate_limit_cache, key, window)

    try:
        count = _increment_rate_counter(cache, key, window)
    except (ConnectionInterrupted, RedisError, TimeoutError, OSError):
        was_open = now >= _redis_unavailable_until
        _redis_unavailable_until = now + _REDIS_FAILURE_COOLDOWN_SECONDS
        if was_open:
            logger.warning(
                "developer_api_rate_limit_redis_unavailable",
                extra={"fallback_cooldown_seconds": _REDIS_FAILURE_COOLDOWN_SECONDS},
            )
        return _increment_rate_counter(_fallback_rate_limit_cache, key, window)

    _redis_unavailable_until = 0.0
    return count


class DeveloperAPIMiddleware:
    """Rate-limit and measure the public developer API namespaces."""
    PREFIXES = ("/api/developer/", "/api/v1/developer/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(self.PREFIXES):
            return self.get_response(request)
        started = time.monotonic()
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.META["HTTP_X_REQUEST_ID"] = request_id
        key_value = request.headers.get("X-API-Key") or request.headers.get("Api-Key")
        api_key = APIKey.objects.filter(key=key_value).first() if key_value else None
        authorization = request.headers.get("Authorization", "").strip()
        if api_key:
            raw_identity = f"key:{api_key.pk}"
        elif authorization.lower().startswith("bearer "):
            # Hash the short-lived JWT instead of storing or exposing the token.
            raw_identity = f"jwt:{hashlib.sha256(authorization.encode('utf-8')).hexdigest()}"
        else:
            raw_identity = f"ip:{request.META.get('REMOTE_ADDR', 'anon')}"
        identity = hashlib.sha256(raw_identity.encode("utf-8")).hexdigest()[:32]
        from django.conf import settings
        limit = int(getattr(settings, "DEVELOPER_API_RATE_LIMIT", 60))
        window = int(getattr(settings, "DEVELOPER_API_RATE_WINDOW", 60))
        cache_key = f"developer:rate:{identity}"
        count = _next_rate_limit_count(cache_key, window)
        if count > limit:
            RateLimitEvent.objects.create(api_key=api_key, identity=identity, path=request.path)
            return JsonResponse({"detail": "Developer API rate limit exceeded", "retry_after": window}, status=429, headers={"Retry-After": str(window), "X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": "0", "X-Request-ID": request_id})
        response = self.get_response(request)
        try:
            APIUsageEvent.objects.create(user=api_key.user if api_key else None, api_key=api_key, method=request.method, path=request.path, status_code=response.status_code, latency_ms=round((time.monotonic() - started) * 1000, 3))
            if api_key:
                APIKey.objects.filter(pk=api_key.pk).update(last_used=timezone.now())
        except Exception:
            logger.warning("Developer API usage tracking failed", exc_info=True)
        response["X-RateLimit-Limit"] = str(limit)
        response["X-RateLimit-Remaining"] = str(max(0, limit - count))
        response["X-Request-ID"] = request_id
        return response
