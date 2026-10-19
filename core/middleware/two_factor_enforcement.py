"""Enforce MFA on already-authenticated browser sessions after enrollment."""
from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from core.models import UserProfile


class TwoFactorEnforcementMiddleware:
    """Require a completed second factor for session-authenticated requests."""

    AUTH_EXEMPT_PATHS = (
        "/login/two-factor/",
        "/logout/",
        "/api/auth/login/",
        "/api/auth/token/",
        "/api/auth/token/refresh/",
        "/api/auth/register/",
        "/api/auth/logout/",
        "/register/",
        "/verify-email/",
        "/forgot-password/",
        "/reset-password/",
        "/auth/google/",
        "/auth/google/callback/",
        "/health/",
        "/static/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        path = request.path_info or "/"
        exempt = any(path == prefix or path.startswith(prefix) for prefix in self.AUTH_EXEMPT_PATHS)
        if user is not None and user.is_authenticated and not exempt:
            profile = UserProfile.objects.filter(user=user).only("two_factor_enabled").first()
            if (
                profile
                and profile.two_factor_enabled
                and str(request.session.get("algobot_mfa_verified_user_id", "")) != str(user.pk)
            ):
                pending_user_id = user.pk
                logout(request)
                request.session["algobot_pending_2fa_user_id"] = pending_user_id
                if path.startswith("/api/"):
                    return JsonResponse({
                        "status": "challenge_required",
                        "code": "two_factor_required",
                        "detail": "Complete second-factor verification to continue.",
                        "next_url": reverse("two_factor_challenge_page"),
                    }, status=403)
                return redirect("two_factor_challenge_page")
        return self.get_response(request)
