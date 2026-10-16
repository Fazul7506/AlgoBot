"""Safe relative redirect helpers for account and broker onboarding flows."""
from django.utils.http import url_has_allowed_host_and_scheme


def safe_auth_destination(request, candidate):
    """Accept only a same-host relative path, never an absolute or protocol-relative URL."""
    candidate = str(candidate or "").strip()
    if not candidate.startswith("/") or candidate.startswith("//") or "\\" in candidate:
        return ""
    if not url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return ""
    return candidate


def first_safe_auth_destination(request, *candidates):
    """Return the first safe candidate without allowing an unsafe value to mask a safe one."""
    for candidate in candidates:
        safe = safe_auth_destination(request, candidate)
        if safe:
            return safe
    return ""
