"""Independent trader-facing workspaces for operational features."""

import hashlib

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils import timezone
from django.shortcuts import redirect, render
from types import SimpleNamespace

from apps.automation.models import ScheduledTask, Workflow, WorkflowExecution
from apps.developer.models import APIKey
from apps.monitoring.models import AuditLog
from apps.observability.models import AuditEvent
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
    """Render a merged, private feed from structured and application audit streams."""
    from datetime import timedelta
    from django.utils.dateparse import parse_date

    structured = AuditLog.objects.filter(user=request.user)
    application = AuditEvent.objects.filter(actor_id=request.user.pk)
    action = request.GET.get("action", "").strip()[:120]
    module = request.GET.get("module", "").strip()[:120]
    search = request.GET.get("q", "").strip()[:160]
    date_range = request.GET.get("range", "7d").strip()[:12]
    severity_filter = request.GET.get("severity", "").strip().lower()[:16]
    start_date = parse_date(request.GET.get("start", ""))
    end_date = parse_date(request.GET.get("end", ""))

    if action:
        structured = structured.filter(action__icontains=action)
        application = application.filter(action__icontains=action)
    if module:
        structured = structured.filter(module__icontains=module)
        application = application.filter(resource_type__icontains=module)
    if search:
        structured = structured.filter(
            Q(action__icontains=search) | Q(module__icontains=search) | Q(resource__icontains=search)
        )
        application = application.filter(
            Q(action__icontains=search) | Q(resource_type__icontains=search) |
            Q(resource_id__icontains=search) | Q(outcome__icontains=search)
        )
    if start_date:
        structured = structured.filter(timestamp__date__gte=start_date)
        application = application.filter(created_at__date__gte=start_date)
    elif date_range in ("24h", "7d", "30d"):
        cutoff = timezone.now() - timedelta(hours=24) if date_range == "24h" else timezone.now() - timedelta(days=7 if date_range == "7d" else 30)
        structured = structured.filter(timestamp__gte=cutoff)
        application = application.filter(created_at__gte=cutoff)
    if end_date:
        structured = structured.filter(timestamp__date__lte=end_date)
        application = application.filter(created_at__date__lte=end_date)

    # Bound cross-model merging to the most recent 1,000 matching records.
    structured_events = list(structured.order_by("-timestamp", "-id")[:500])
    application_events = list(application.order_by("-created_at", "-id")[:500])
    actor_ids = {event.actor_id for event in application_events if event.actor_id}
    if actor_ids:
        from django.contrib.auth import get_user_model
        actor_names = {
            user.pk: user.get_username()
            for user in get_user_model().objects.filter(pk__in=actor_ids)
        }
    else:
        actor_names = {}
    merged = [
        SimpleNamespace(
            pk=event.pk, action=event.action, module=event.module, resource=event.resource,
            timestamp=event.timestamp, hash=event.hash, source="Structured audit",
            username=event.user.get_username() if event.user_id else "System",
            ip_address=event.ip_address, outcome="", severity="info",
        )
        for event in structured_events
    ]
    merged.extend(
        SimpleNamespace(
            pk=event.pk, action=event.action, module=event.resource_type or "application",
            resource=f"{event.resource_id or '—'} · outcome={event.outcome}",
            timestamp=event.created_at, hash="", source="Application event",
            username=actor_names.get(event.actor_id, "System" if not event.actor_id else "Unknown user"),
            ip_address=event.ip_address,
            outcome=str(event.outcome or ""), severity="info",
        )
        for event in application_events
    )
    for event in merged:
        label = f"{event.action} {event.module} {event.outcome}".lower()
        if any(term in label for term in ("failed", "failure", "denied", "error", "blocked", "security alert")):
            event.severity = "high"
        elif any(term in label for term in ("withdraw", "risk", "permission", "password", "changed", "delete", "revoke")):
            event.severity = "medium"
        elif any(term in label for term in ("trade", "order", "api", "connect", "login", "create", "update")):
            event.severity = "low"
    merged.sort(key=lambda event: (event.timestamp, str(event.pk)), reverse=True)
    if severity_filter in ("info", "low", "medium", "high"):
        merged = [event for event in merged if event.severity == severity_filter]
    if request.GET.get("export") == "csv":
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="algobot-audit-log.csv"'
        writer = csv.writer(response)
        writer.writerow(["Timestamp", "Event", "User", "Source", "Details", "Severity"])
        for event in merged:
            writer.writerow([
                event.timestamp.isoformat() if event.timestamp else "",
                event.action,
                request.user.get_username(),
                event.source,
                event.resource,
                event.severity.title(),
            ])
        return response
    summary = {
        level: sum(1 for event in merged if event.severity == level)
        for level in ("info", "low", "medium", "high")
    }
    summary_percent = {
        level: round((count / len(merged)) * 100, 1) if merged else 0
        for level, count in summary.items()
    }
    recent_events = [
        SimpleNamespace(action=event.action, module=event.module, timestamp=event.timestamp, severity=event.severity)
        for event in merged[:5]
    ]
    from django.core.paginator import Paginator
    page = Paginator(merged, 10).get_page(request.GET.get("page", 1))
    return render(request, "core/audit_log.html", {
        "events": page.object_list, "event_count": len(merged), "page_obj": page,
        "audit_filters": {"action": action, "module": module, "q": search, "range": date_range,
                          "severity": severity_filter, "start": request.GET.get("start", ""),
                          "end": request.GET.get("end", "")},
        "event_summary": summary, "event_summary_percent": summary_percent, "recent_events": recent_events,
    })

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
                    # Revoke pre-enrollment refresh tokens in a bounded number of
                    # database queries; per-token get_or_create made enrollment
                    # latency grow linearly with the account's token history.
                    outstanding_ids = OutstandingToken.objects.filter(
                        user=request.user,
                    ).exclude(
                        id__in=BlacklistedToken.objects.filter(
                            token__user=request.user,
                        ).values("token_id"),
                    ).values_list("id", flat=True)
                    BlacklistedToken.objects.bulk_create(
                        [BlacklistedToken(token_id=token_id) for token_id in outstanding_ids],
                        ignore_conflicts=True,
                    )
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

    # Security Center activity is drawn only from persisted, user-scoped audit
    # records. Do not synthesize login attempts or expose another user's events.
    security_audit_logs = list(AuditLog.objects.filter(user=request.user).order_by("-timestamp", "-id")[:30])
    security_audit_events = list(AuditEvent.objects.filter(actor_id=request.user.pk).order_by("-created_at", "-id")[:30])
    security_events = [
        SimpleNamespace(
            timestamp=item.timestamp, action=item.action, module=item.module,
            details=item.resource or "—", outcome="recorded", source="Audit log",
        ) for item in security_audit_logs
    ]
    security_events.extend(
        SimpleNamespace(
            timestamp=item.created_at, action=item.action,
            module=item.resource_type or "application",
            details=item.resource_id or "—", outcome=item.outcome or "unknown",
            source="Application event",
        ) for item in security_audit_events
    )
    security_events.sort(key=lambda item: item.timestamp, reverse=True)
    security_events = security_events[:12]
    login_events = [item for item in security_events if any(
        term in (str(item.action) + " " + str(item.module)).lower()
        for term in ("login", "sign-in", "signin", "auth", "session", "password")
    )][:6]
    # A concise alert list can only be derived from recorded failed/blocked auth
    # events. The underlying audit trail is preserved and remains user-scoped.
    security_alerts = [item for item in login_events if any(
        term in (str(item.action) + " " + str(item.outcome)).lower()
        for term in ("fail", "denied", "blocked", "rejected", "suspicious")
    )][:3]
    user_agent = (request.META.get("HTTP_USER_AGENT") or "Current browser")[:180]
    current_device = "Mobile browser" if any(term in user_agent.lower() for term in ("android", "iphone", "mobile")) else "Desktop or tablet browser"
    secure_session = bool(
        getattr(settings, "SESSION_COOKIE_SECURE", False)
        and getattr(settings, "CSRF_COOKIE_SECURE", False)
    )
    # The account-security summary must not treat broker connectivity or API-key
    # expiry as proof of personal account security. Use only account/auth state.
    checks = [
        ("Account enabled", bool(request.user.is_active)),
        ("Email verification", bool(profile.email_verified)),
        ("Secure session cookies", secure_session),
        ("Two-factor authentication", bool(profile.two_factor_enabled)),
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
            "two_factor_recovery_codes_remaining": sum(1 for item in (profile.two_factor_recovery_codes or []) if not (isinstance(item, dict) and item.get("used", False))),
            "two_factor_recovery_code_statuses": [{"used": bool(item.get("used", False)) if isinstance(item, dict) else False, "number": index + 1} for index, item in enumerate(profile.two_factor_recovery_codes or [])],
            "password_required": request.user.has_usable_password(),
            "security_events": security_events,
            "login_events": login_events,
            "security_alerts": security_alerts,
            "current_device": current_device,
        },
    )
    # Enrollment URIs and one-time recovery codes must not be cached by browsers.
    response["Cache-Control"] = "no-store, private"
    response["Pragma"] = "no-cache"
    return response
