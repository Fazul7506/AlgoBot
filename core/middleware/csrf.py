from django.middleware.csrf import CsrfViewMiddleware


class APIAwareCsrfViewMiddleware(CsrfViewMiddleware):
    """Keep CSRF for cookie-authenticated browsers, exempt header-auth APIs."""

    API_PREFIXES = ("/api/", "/data/")

    def process_view(self, request, callback, callback_args, callback_kwargs):
        if request.path.startswith(self.API_PREFIXES):
            authorization = str(request.headers.get("Authorization") or "").strip().lower()
            api_key = str(request.headers.get("X-API-Key") or request.headers.get("Api-Key") or "").strip()
            if authorization.startswith("bearer ") or api_key:
                request.csrf_processing_done = True
                return None
        return super().process_view(request, callback, callback_args, callback_kwargs)
