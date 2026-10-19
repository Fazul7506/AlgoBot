"""Independent trader-facing workspaces for operational features."""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils import timezone
from django.shortcuts import redirect, render

from apps.automation.models import ScheduledTask, Workflow, WorkflowExecution
from apps.developer.models import APIKey
from apps.monitoring.models import AuditLog
from core.account_context import get_active_account


def _account(request):
    return get_active_account(request.user, request=request)


@login_required
def automation_workspace(request):
    workflows = Workflow.objects.filter(user=request.user).order_by("-updated_at", "-id")
    executions = WorkflowExecution.objects.filter(workflow__user=request.user)
    schedules = ScheduledTask.objects.filter(workflow__user=request.user, status__in=["pending", "running"])
    return render(request, "core/automation_workspace.html", {"workflows": workflows[:20], "running": executions.filter(status="running").count(), "failed": executions.filter(status="failed").count(), "scheduled": schedules.count()})


@login_required
def audit_workspace(request):
    events = AuditLog.objects.filter(user=request.user).order_by("-timestamp")[:80]
    return render(request, "core/audit_log.html", {"events": events, "event_count": AuditLog.objects.filter(user=request.user).count()})


@login_required
def security_workspace(request):
    from django.contrib import messages
    from django.contrib.auth import update_session_auth_hash
    from django.db import transaction
    from core.models import UserProfile
    from core.services.two_factor_service import (
        TwoFactorService, generate_recovery_codes, verify_user_code,
    )
    from core.auth_rate_limit import allow_auth_attempt

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    setup_uri = ""
    recovery_codes = request.session.pop("algobot_2fa_recovery_codes_once", [])
    if request.method == "POST":
        action = str(request.POST.get("security_action") or "").strip()
        if action == "setup_2fa":
            if profile.two_factor_enabled:
                messages.info(request, "Two-factor authentication is already enabled.")
            elif request.user.has_usable_password() and not request.user.check_password(request.POST.get("current_password") or ""):
                messages.error(request, "Enter your current password before starting two-factor setup.")
            else:
                try:
                    pending_secret = TwoFactorService.generate_secret()
                    profile.two_factor_pending_secret_encrypted = TwoFactorService.encrypt_secret(pending_secret)
                    profile.save(update_fields=["two_factor_pending_secret_encrypted", "updated_at"])
                    setup_uri = TwoFactorService(pending_secret).get_uri(request.user.email or request.user.username, issuer="AlgoBot")
                    request.session["algobot_2fa_setup_uri"] = setup_uri
                    messages.info(request, "Add this account to your authenticator app, then enter its current six-digit code to finish setup.")
                except (RuntimeError, ValueError):
                    messages.error(request, "Two-factor setup is unavailable until the server encryption key is configured correctly.")
        elif action == "verify_2fa":
            if not (
                allow_auth_attempt(request, "two-factor-enrollment", str(request.user.pk), limit=10, window=900)
                and allow_auth_attempt(request, "two-factor-enrollment-ip", "", limit=30, window=900)
            ):
                messages.error(request, "Too many authenticator verification attempts. Wait before trying again.")
                return redirect("security_center")
            try:
                pending_secret = TwoFactorService.decrypt_secret(profile.two_factor_pending_secret_encrypted)
                if pending_secret and TwoFactorService(pending_secret).validate_token(request.POST.get("two_factor_code")):
                    recovery_codes, recovery_hashes = generate_recovery_codes()
                    profile.two_factor_secret_encrypted = profile.two_factor_pending_secret_encrypted
                    profile.two_factor_pending_secret_encrypted = ""
                    profile.two_factor_recovery_codes = recovery_hashes
                    profile.two_factor_enabled = True
                    profile.save(update_fields=[
                        "two_factor_secret_encrypted", "two_factor_pending_secret_encrypted",
                        "two_factor_recovery_codes", "two_factor_enabled", "updated_at",
                    ])
                    # Enrollment itself just verified the authenticator, so this
                    # browser session may request its browser-scoped API token.
                    request.session["algobot_mfa_verified_user_id"] = request.user.pk
                    # Refresh credentials minted before MFA enrollment must not
                    # remain a way to bypass the newly enabled second factor.
                    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
                    for outstanding in OutstandingToken.objects.filter(user=request.user):
                        BlacklistedToken.objects.get_or_create(token=outstanding)
                    request.session["algobot_2fa_recovery_codes_once"] = recovery_codes
                    messages.success(request, "Two-factor authentication is enabled. Save these recovery codes now; they are shown only once.")
                    return redirect("security_center")
                messages.error(request, "That code could not be verified. Check your authenticator's current code and try again.")
            except RuntimeError:
                messages.error(request, "Two-factor setup is unavailable until the server encryption key is configured correctly.")
        elif action == "disable_2fa":
            if not (
                allow_auth_attempt(request, "two-factor-disable", str(request.user.pk), limit=10, window=900)
                and allow_auth_attempt(request, "two-factor-disable-ip", "", limit=30, window=900)
            ):
                messages.error(request, "Too many authenticator verification attempts. Wait before trying again.")
                return redirect("security_center")
            current_password = request.POST.get("current_password") or ""
            code = request.POST.get("two_factor_code") or ""
            password_valid = (
                not request.user.has_usable_password()
                or request.user.check_password(current_password)
            )
            if not password_valid:
                messages.error(request, "Enter your current password to disable two-factor authentication.")
            elif not profile.two_factor_enabled or not verify_user_code(profile, code, consume_recovery=True):
                messages.error(request, "A valid authenticator or unused recovery code is required.")
            else:
                profile.two_factor_enabled = False
                profile.two_factor_secret_encrypted = ""
                profile.two_factor_pending_secret_encrypted = ""
                profile.two_factor_recovery_codes = []
                profile.save(update_fields=[
                    "two_factor_enabled", "two_factor_secret_encrypted",
                    "two_factor_pending_secret_encrypted", "two_factor_recovery_codes", "updated_at",
                ])
                messages.success(request, "Two-factor authentication has been disabled.")
        elif action == "regenerate_recovery_codes":
            if not (
                allow_auth_attempt(request, "two-factor-recovery-regenerate", str(request.user.pk), limit=5, window=900)
                and allow_auth_attempt(request, "two-factor-recovery-regenerate-ip", "", limit=20, window=900)
            ):
                messages.error(request, "Too many recovery-code requests. Wait before trying again.")
                return redirect("security_center")
            current_password = request.POST.get("current_password") or ""
            code = request.POST.get("two_factor_code") or ""
            password_valid = (
                not request.user.has_usable_password()
                or request.user.check_password(current_password)
            )
            if not password_valid:
                messages.error(request, "Enter your current password to regenerate recovery codes.")
            elif not profile.two_factor_enabled or not verify_user_code(profile, code, consume_recovery=True):
                messages.error(request, "A valid authenticator or unused recovery code is required.")
            else:
                recovery_codes, recovery_hashes = generate_recovery_codes()
                profile.two_factor_recovery_codes = recovery_hashes
                profile.save(update_fields=["two_factor_recovery_codes", "updated_at"])
                request.session["algobot_2fa_recovery_codes_once"] = recovery_codes
                messages.success(request, "Recovery codes were regenerated. Save this new set; previous codes no longer work.")
        return redirect("security_center")

    setup_uri = request.session.pop("algobot_2fa_setup_uri", "")
    if not setup_uri and profile.two_factor_pending_secret_encrypted:
        try:
            pending_secret = TwoFactorService.decrypt_secret(profile.two_factor_pending_secret_encrypted)
            setup_uri = TwoFactorService(pending_secret).get_uri(
                request.user.email or request.user.username, issuer="AlgoBot"
            )
        except RuntimeError:
            setup_uri = ""
    account = _account(request)
    keys = APIKey.objects.filter(user=request.user)
    now = timezone.now()
    usable_keys = keys.filter(status="active").filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    expired_active_keys = keys.filter(status="active", expires_at__lte=now).exists()
    account_connected = bool(account and account.is_connection_eligible)
    secure_session = bool(
        getattr(settings, "SESSION_COOKIE_SECURE", False)
        and getattr(settings, "CSRF_COOKIE_SECURE", False)
    )
    checks = [
        ("Broker connection", account_connected),
        ("Secure session cookies", secure_session),
        ("Account sign-in", bool(request.user.is_active and request.user.has_usable_password())),
        ("Developer key expiry", not expired_active_keys),
        ("Two-factor authentication", profile.two_factor_enabled),
    ]
    response = render(
        request,
        "core/security_center.html",
        {
            "account": account,
            "account_connected": account_connected,
            "keys_count": usable_keys.count(),
            "checks": checks,
            "checks_ok": all(ok for _, ok in checks),
            "two_factor_enabled": profile.two_factor_enabled,
            "two_factor_setup_pending": bool(profile.two_factor_pending_secret_encrypted),
            "two_factor_setup_uri": setup_uri,
            "two_factor_recovery_codes": recovery_codes,
            "two_factor_recovery_codes_remaining": len(profile.two_factor_recovery_codes or []),
            "password_required": request.user.has_usable_password(),
        },
    )
    # Enrollment URIs and one-time recovery codes must not be cached by browsers.
    response["Cache-Control"] = "no-store, private"
    response["Pragma"] = "no-cache"
    return response
