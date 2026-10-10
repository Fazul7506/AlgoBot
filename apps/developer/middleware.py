import hashlib
import logging
import time
import uuid
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from .models import APIKey, APIUsageEvent, RateLimitEvent

logger = logging.getLogger(__name__)


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
        if cache.add(cache_key, 1, window):
            count = 1
        else:
            try:
                count = cache.incr(cache_key)
            except (ValueError, TypeError):
                # A cache restart must not make the endpoint fail closed.
                cache.set(cache_key, 1, window)
                count = 1
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
