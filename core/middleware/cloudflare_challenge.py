"""Canonicalize Cloudflare challenge query parameters after edge clearance.

Cloudflare may append internal ``__cf_chl_*`` query parameters while solving an
interstitial challenge. They are edge state, not AlgoBot application inputs.
Once a request reaches Django, GET/HEAD navigation is redirected to the clean
canonical URL so challenge tokens are never retained as application state.
POST/PUT/PATCH/DELETE requests are deliberately left untouched.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.http import HttpResponseRedirect


class CloudflareChallengeQueryMiddleware:
    """Remove Cloudflare internal challenge parameters from safe navigation."""

    PREFIX = "__cf_chl_"

    def __init__(self, get_response):
        self.get_response = get_response

    @classmethod
    def clean_query(cls, query):
        pairs = parse_qsl(query or "", keep_blank_values=True)
        cleaned = [(name, value) for name, value in pairs if not name.startswith(cls.PREFIX)]
        return urlencode(cleaned, doseq=True)

    def __call__(self, request):
        if request.method in {"GET", "HEAD"}:
            query = request.META.get("QUERY_STRING", "")
            # Do not canonicalize arbitrary application query strings. Signed
            # email-verification tokens may contain characters that urlencode
            # escapes; redirecting those requests before the view runs breaks
            # the scanner-safe confirmation page (and can alter token URLs).
            pairs = parse_qsl(query or "", keep_blank_values=True)
            has_challenge_parameter = any(name.startswith(self.PREFIX) for name, _ in pairs)
            if has_challenge_parameter:
                cleaned = self.clean_query(query)
                parts = urlsplit(request.get_full_path())
                canonical = urlunsplit(("", "", parts.path, cleaned, parts.fragment))
                response = HttpResponseRedirect(canonical)
                response["Cache-Control"] = "no-store"
                return response
        return self.get_response(request)