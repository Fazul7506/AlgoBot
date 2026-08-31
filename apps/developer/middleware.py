import time
import uuid
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from .models import APIKey, APIUsageEvent, RateLimitEvent


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
        identity = key_value or request.META.get("REMOTE_ADDR", "anon")
        from django.conf import settings
        limit = int(getattr(settings, "DEVELOPER_API_RATE_LIMIT", 60))
        window = int(getattr(settings, "DEVELOPER_API_RATE_WINDOW", 60))
        cache_key = f"developer:rate:{identity}"
        count = cache.get(cache_key, 0)
        if count >= limit:
            RateLimitEvent.objects.create(api_key=api_key, identity=str(identity), path=request.path)
            return JsonResponse({"detail": "Developer API rate limit exceeded", "retry_after": window}, status=429, headers={"Retry-After": str(window), "X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": "0", "X-Request-ID": request_id})
        cache.set(cache_key, count + 1, window)
        response = self.get_response(request)
        try:
            APIUsageEvent.objects.create(user=api_key.user if api_key else None, api_key=api_key, method=request.method, path=request.path, status_code=response.status_code, latency_ms=round((time.monotonic() - started) * 1000, 3))
            if api_key:
                APIKey.objects.filter(pk=api_key.pk).update(last_used=timezone.now())
        except Exception:
            pass
        response["X-RateLimit-Limit"] = str(limit)
        response["X-RateLimit-Remaining"] = str(max(0, limit - count - 1))
        response["X-Request-ID"] = request_id
        return response
