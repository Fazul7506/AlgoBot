import time
from django.core.cache import cache
from django.http import JsonResponse
from .models import APIKey, APIUsageEvent, RateLimitEvent

class DeveloperAPIMiddleware:
    """Rate-limit and measure the developer API without affecting normal app routes."""
    PREFIX = "/api/developer/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(self.PREFIX):
            return self.get_response(request)
        started = time.monotonic()
        key_value = request.headers.get("X-API-Key") or request.headers.get("Api-Key")
        api_key = None
        identity = request.META.get("REMOTE_ADDR", "anon")
        if key_value:
            api_key = APIKey.objects.filter(key=key_value).first()
            identity = key_value
        from django.conf import settings
        limit = int(getattr(settings, "DEVELOPER_API_RATE_LIMIT", 60))
        window = int(getattr(settings, "DEVELOPER_API_RATE_WINDOW", 60))
        cache_key = f"developer:rate:{identity}"
        count = cache.get(cache_key, 0)
        if count >= limit:
            RateLimitEvent.objects.create(api_key=api_key, identity=str(identity), path=request.path)
            return JsonResponse({"detail": "Developer API rate limit exceeded", "retry_after": window}, status=429)
        cache.set(cache_key, count + 1, window)
        response = self.get_response(request)
        try:
            APIUsageEvent.objects.create(
                user=api_key.user if api_key else None,
                api_key=api_key,
                method=request.method,
                path=request.path,
                status_code=response.status_code,
                latency_ms=round((time.monotonic() - started) * 1000, 3),
            )
            if api_key:
                APIKey.objects.filter(pk=api_key.pk).update(last_used=__import__("django.utils.timezone", fromlist=["now"]).now())
        except Exception:
            pass
        response["X-RateLimit-Limit"] = str(limit)
        response["X-RateLimit-Remaining"] = str(max(0, limit - count - 1))
        return response
