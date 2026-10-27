"""Browser-facing local account authentication and recovery flows.

Broker OAuth is intentionally separate from AlgoBot login, registration,
password recovery, and email verification.
"""
import hashlib
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from core.auth_redirects import first_safe_auth_destination

from core.models import BotSettings, GoogleIdentity, PasswordResetToken, Subscription, UserProfile
from core.auth_rate_limit import allow_auth_attempt

logger = logging.getLogger("account_auth")
RESET_TTL = timedelta(hours=1)
VERIFICATION_RESEND_COOLDOWN = timedelta(seconds=60)
PENDING_VERIFICATION_EMAIL_SESSION_KEY = "algobot_pending_verification_email"


def _digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _render(request, mode, **context):
    context["next"] = first_safe_auth_destination(
        request,
        context.get("next"),
        request.GET.get("next"),
        request.POST.get("next"),
        request.session.get("broker_onboarding_next", ""),
    )
    return render(request, "core/auth_page.html", {"mode": mode, **context})


def _public_url(request, path):
    """Build email links from the configured canonical origin, not an arbitrary Host header."""
    base_url = str(getattr(settings, "BASE_URL", "") or "").strip().rstrip("/")
    if base_url:
        if not getattr(settings, "DEBUG", False) and not base_url.startswith("https://"):
            logger.error("auth_public_base_url_must_use_https")
            return ""
        return base_url + (path if path.startswith("/") else "/" + path)
    return request.build_absolute_uri(path)


def _send_account_email(subject, body, email, *, metadata=None):
    try:
        # Reuse AlgoBot's configured transactional delivery path (Brevo when
        # configured, Django email backend otherwise) for auth/security mail.
        from apps.notifications.services import send_transactional_email
        provider = send_transactional_email(
            recipient=email, subject=subject, message=body,
            category="authentication", metadata=metadata,
        )
        # Log provider acceptance only; never log the recipient, message body,
        # verification URL, or any token. Provider acceptance is not inbox proof.
        logger.info("account_email_provider_accepted provider=%s", provider)
        return True
    except Exception as exc:
        # Provider exceptions can include recipient addresses, request details,
        # or response bodies. Keep auth-mail diagnostics useful but sanitized.
        logger.error(
            "account_email_delivery_failed error_type=%s",
            exc.__class__.__name__,
            extra={"error_type": exc.__class__.__name__},
        )
        return False


def _send_verification(request, user, profile, *, recipient=None, purpose="verify_email", extra_payload=None):
    payload = {
        "uid": user.pk,
        "purpose": purpose,
        "nonce": secrets.token_urlsafe(24),
    }
    if extra_payload:
        payload.update(extra_payload)
    raw_token = signing.dumps(payload, salt="algobot-email-verification")
    profile.email_verification_token = _digest(raw_token)
    profile.email_verification_token_created_at = timezone.now()
    profile.save(update_fields=["email_verification_token", "email_verification_token_created_at", "updated_at"])
    link = _public_url(
        request, reverse("verify_email_page") + "?" + urlencode({"token": raw_token})
    )
    if not link:
        logger.error("verification_email_not_sent_due_to_invalid_base_url")
        return False
    email = str(recipient or user.email or "").strip().lower()
    if purpose == "change_email":
        subject = "Confirm your new AlgoBot email address"
        body = (
            "We received a request to change the email address on your AlgoBot account. "
            "Use the secure button in the HTML version of this message to confirm the new address. "
            "Your current email remains unchanged until confirmation. If you did not request this, "
            "you can ignore this message."
        )
        action_label = "Confirm new email address"
    else:
        subject = "Verify your AlgoBot email address"
        body = (
            "Welcome to AlgoBot. Use the secure Verify Email button in the HTML version of this "
            "message to verify your email address. If you did not create this account, you can "
            "ignore this message."
        )
        action_label = "Verify email address"
    return _send_account_email(
        subject, body, email,
        metadata={"action_url": link, "action_label": action_label},
    )


def login_page(request):
    safe_destination = first_safe_auth_destination(
        request,
        request.POST.get("next"),
        request.GET.get("next"),
        request.session.get("broker_onboarding_next", ""),
    )
    if request.user.is_authenticated:
        from core.broker_onboarding import has_authorized_broker_connection, has_verified_account_email
        if not has_verified_account_email(request.user):
            request.session[PENDING_VERIFICATION_EMAIL_SESSION_KEY] = request.user.email
            messages.info(request, "Verify your AlgoBot email before continuing.")
            return redirect("verify_email_page")
        if not has_authorized_broker_connection(request.user):
            if safe_destination:
                request.session["broker_onboarding_next"] = safe_destination
            return redirect("broker_marketplace_page")
        if safe_destination and not safe_destination.startswith(("/login/", "/register/", "/auth/google/")):
            return redirect(safe_destination)
        return redirect("dashboard_page")
    if request.method == "POST":
        identifier = str(request.POST.get("identifier") or request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        identifier_allowed = allow_auth_attempt(request, "password-login", identifier, limit=10, window=900)
        ip_allowed = allow_auth_attempt(request, "password-login-ip", "", limit=30, window=900)
        if not identifier_allowed or not ip_allowed:
            from core.auth_audit import record_auth_event
            record_auth_event(request, action="Login throttled", outcome="blocked", identifier=identifier)
            messages.error(request, "Too many sign-in attempts. Please wait and try again.")
            return _render(request, "login", identifier=identifier)
        user = None
        if identifier and password:
            if "@" in identifier:
                matches = User.objects.filter(email__iexact=identifier)
                if matches.count() == 1:
                    user = authenticate(request, username=matches.first().get_username(), password=password)
            else:
                user = authenticate(request, username=identifier, password=password)
                if user is None:
                    matches = User.objects.filter(username__iexact=identifier)
                    if matches.count() == 1:
                        user = authenticate(request, username=matches.first().get_username(), password=password)
        if user is None:
            from core.auth_audit import record_auth_event
            record_auth_event(request, action="Login failed", outcome="failed", identifier=identifier)
            request.session.pop("algobot_pending_2fa_user_id", None)
            messages.error(request, "The username/email or password is incorrect.")
            return _render(request, "login", identifier=identifier)
        pending_2fa_user_id = request.session.get("algobot_pending_2fa_user_id")
        if pending_2fa_user_id and str(pending_2fa_user_id) != str(user.pk):
            from core.auth_audit import record_auth_event
            record_auth_event(request, action="Login failed", outcome="failed", user=user)
            request.session.pop("algobot_pending_2fa_user_id", None)
            messages.error(request, "The username/email or password is incorrect.")
            return _render(request, "login", identifier=identifier)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if not profile.email_verified:
            request.session[PENDING_VERIFICATION_EMAIL_SESSION_KEY] = user.email
            messages.info(request, "Please verify your email before signing in. Your account email is ready below.")
            return redirect("verify_email_page")
        if profile.two_factor_enabled:
            from core.services.two_factor_service import verify_user_code
            code = request.POST.get("two_factor_code") or ""
            if not code:
                request.session["algobot_pending_2fa_user_id"] = user.pk
                return _render(request, "login", identifier=identifier, mfa_required=True)
            if not verify_user_code(profile, code, consume_recovery=True):
                from core.auth_audit import record_auth_event
                record_auth_event(request, action="Two-factor verification failed", outcome="failed", user=user)
                request.session["algobot_pending_2fa_user_id"] = user.pk
                return _render(
                    request, "login", identifier=identifier, mfa_required=True,
                    errors=["The authenticator or recovery code is invalid. Try again."],
                )
        request.session.pop("algobot_pending_2fa_user_id", None)
        auth_login(request, user)
        from core.auth_audit import record_auth_event
        record_auth_event(request, action="Login successful", outcome="success", user=user)
        if profile.two_factor_enabled:
            request.session["algobot_mfa_verified_user_id"] = user.pk
        UserProfile.objects.update_or_create(user=user, defaults={"last_login_at": timezone.now()})
        from core.broker_onboarding import has_authorized_broker_connection
        safe_destination = first_safe_auth_destination(
            request,
            request.POST.get("next"),
            request.GET.get("next"),
            request.session.get("broker_onboarding_next", ""),
        )
        if safe_destination.startswith(("/login/", "/register/", "/auth/google/")):
            safe_destination = ""
        if not has_authorized_broker_connection(user):
            if safe_destination:
                request.session["broker_onboarding_next"] = safe_destination
                # Resume an explicitly initiated Deriv connection after login.
                if safe_destination.startswith("/brokers/connect/"):
                    return redirect(safe_destination)
            return redirect("broker_marketplace_page")
        if safe_destination:
            return redirect(safe_destination)
        return redirect("dashboard_page")
    return _render(request, "login", next=request.GET.get("next", ""))


def register_page(request):
    requested_next = first_safe_auth_destination(
        request,
        request.POST.get("next"),
        request.GET.get("next"),
        request.session.get("broker_onboarding_next", ""),
    )
    if requested_next:
        request.session["broker_onboarding_next"] = requested_next
    if request.user.is_authenticated:
        from core.broker_onboarding import has_authorized_broker_connection, has_verified_account_email
        if not has_verified_account_email(request.user):
            request.session[PENDING_VERIFICATION_EMAIL_SESSION_KEY] = request.user.email
            messages.info(request, "Verify your AlgoBot email before continuing.")
            return redirect("verify_email_page")
        return redirect("dashboard_page" if has_authorized_broker_connection(request.user) else "broker_marketplace_page")
    if request.method == "POST":
        registration_identifier = str(request.POST.get("email") or request.POST.get("username") or "").strip().lower()
        identity_allowed = allow_auth_attempt(request, "registration-identity", registration_identifier, limit=5, window=3600)
        ip_allowed = allow_auth_attempt(request, "registration-ip", "", limit=10, window=3600)
        if not identity_allowed or not ip_allowed:
            return _render(request, "register", errors=["Too many registration attempts. Please try again later."])
        username = str(request.POST.get("username") or "").strip()
        first_name = str(request.POST.get("first_name") or "").strip()
        last_name = str(request.POST.get("last_name") or "").strip()
        email = str(request.POST.get("email") or "").strip().lower()
        password = request.POST.get("password") or ""
        confirm = request.POST.get("password_confirm") or ""
        errors = []
        if not username or not first_name or not last_name or not email or not password:
            errors.append("Username, first name, last name, email, and password are required.")
        if password != confirm:
            errors.append("The passwords do not match.")
        try:
            if username:
                User._meta.get_field("username").clean(username, None)
            if email:
                validate_email(email)
        except ValidationError as exc:
            errors.extend(exc.messages)
        if (
            (username and User.objects.filter(username__iexact=username).exists())
            or (email and User.objects.filter(email__iexact=email).exists())
        ):
            errors.append("An account could not be created with those details. If you already have an account, sign in or use account recovery.")
        candidate = User(username=username, email=email, first_name=first_name, last_name=last_name)
        if password:
            try:
                validate_password(password, user=candidate)
            except ValidationError as exc:
                errors.extend(exc.messages)
        if errors:
            return _render(request, "register", errors=errors, username=username, first_name=first_name, last_name=last_name, email=email)
        try:
            with transaction.atomic():
                user = User.objects.create_user(username=username, email=email, password=password, first_name=first_name, last_name=last_name)
                profile, _ = UserProfile.objects.get_or_create(user=user)
                Subscription.objects.get_or_create(user=user)
                BotSettings.objects.get_or_create(user=user)
            email_sent = _send_verification(request, user, profile)
        except IntegrityError:
            return _render(
                request, "register",
                errors=["An account could not be created with those details. If you already have an account, sign in or use account recovery."],
                username=username, first_name=first_name, last_name=last_name, email=email,
            )
        request.session[PENDING_VERIFICATION_EMAIL_SESSION_KEY] = user.email
        if email_sent:
            messages.success(request, "Your account was created. We sent a verification email. Use the resend control below if it does not arrive.")
        else:
            messages.warning(request, "Your account was created, but the verification email could not be sent. Use the resend option on the verification page when it becomes available.")
        return redirect("verify_email_page")
    return _render(request, "register")


def forgot_password_page(request):
    if request.method == "POST":
        email = str(request.POST.get("email") or "").strip().lower()
        # Always return the same public message to avoid account enumeration.
        email_allowed = allow_auth_attempt(request, "password-reset", email, limit=5, window=3600)
        ip_allowed = allow_auth_attempt(request, "password-reset-ip", "", limit=15, window=3600)
        rate_allowed = email_allowed and ip_allowed
        if email and rate_allowed:
            matches = User.objects.filter(email__iexact=email, is_active=True)
            if matches.count() == 1:
                user = matches.first()
                raw_token = secrets.token_urlsafe(32)
                PasswordResetToken.objects.create(
                    user=user, token=_digest(raw_token),
                    expires_at=timezone.now() + RESET_TTL,
                )
                link = _public_url(
                    request, reverse("reset_password_page", kwargs={"token": raw_token})
                )
                if not link:
                    logger.error("password_reset_email_not_sent_due_to_invalid_base_url")
                    messages.info(request, "If an active account matches that email, password-reset instructions will be sent.")
                    return redirect("forgot_password_page")
                _send_account_email(
                    "Reset your AlgoBot password",
                    "A password reset was requested for your AlgoBot account. "
                    "This link expires in one hour:\n\n"
                    + link
                    + "\n\nIf you did not request this, ignore this message.",
                    user.email,
                )
        messages.info(request, "If an active account matches that email, password-reset instructions will be sent.")
        return redirect("forgot_password_page")
    return _render(request, "forgot_password")


def reset_password_page(request, token=None):
    raw_token = str(token or request.GET.get("token") or "")
    reset = PasswordResetToken.objects.filter(token=_digest(raw_token)).select_related("user").first() if raw_token else None
    valid = bool(reset and reset.is_valid() and reset.user.is_active)
    if not valid:
        return _render(request, "reset_password", token=raw_token, invalid=True)
    if request.method == "POST":
        identity_allowed = allow_auth_attempt(request, "password-reset-submit", raw_token, limit=10, window=900)
        ip_allowed = allow_auth_attempt(request, "password-reset-submit-ip", "", limit=20, window=900)
        if not identity_allowed or not ip_allowed:
            return _render(request, "reset_password", token=raw_token, invalid=True)
        password = request.POST.get("password") or ""
        confirm = request.POST.get("password_confirm") or ""
        if password != confirm:
            return _render(request, "reset_password", token=raw_token, errors=["The passwords do not match."])
        try:
            validate_password(password, user=reset.user)
        except ValidationError as exc:
            return _render(request, "reset_password", token=raw_token, errors=exc.messages)
        now = timezone.now()
        with transaction.atomic():
            locked = PasswordResetToken.objects.select_for_update().select_related("user").filter(pk=reset.pk).first()
            if not locked or not locked.is_valid() or not locked.user.is_active:
                return _render(request, "reset_password", token=raw_token, invalid=True)
            locked.user.set_password(password)
            locked.user.save(update_fields=["password"])
            PasswordResetToken.objects.filter(user=locked.user, used=False).update(used=True, used_at=now)
            # Password recovery invalidates every existing refresh token just
            # like an authenticated password change does.
            from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
            for outstanding in OutstandingToken.objects.filter(user=locked.user):
                BlacklistedToken.objects.get_or_create(token=outstanding)
        auth_logout(request)
        messages.success(request, "Your password has been reset. Sign in with your new password.")
        return redirect("login_page")
    return _render(request, "reset_password", token=raw_token)


def account_identity_page(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if request.method == "POST" and request.POST.get("identity_action") == "change_password":
        current_password = request.POST.get("current_password") or ""
        new_password = request.POST.get("new_password") or ""
        confirm_password = request.POST.get("confirm_password") or ""
        errors = []
        if user.has_usable_password() and not user.check_password(current_password):
            errors.append("Your current password is incorrect.")
        if len(new_password) < 12:
            errors.append("Use at least 12 characters for your new password.")
        if new_password != confirm_password:
            errors.append("The new password and confirmation do not match.")
        try:
            validate_password(new_password, user=user)
        except ValidationError as exc:
            errors.extend(exc.messages)
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            user.set_password(new_password)
            user.save(update_fields=["password"])
            update_session_auth_hash(request, user)
            messages.success(request, "Your password has been changed.")
        return redirect("account_identity_page")
    if request.method == "POST":
        current_password = request.POST.get("current_password") or ""
        username = str(request.POST.get("username") or "").strip()
        email = str(request.POST.get("email") or "").strip().lower()
        errors = []
        if user.has_usable_password() and not user.check_password(current_password):
            errors.append("Enter your current password to change account identity.")
        if not username:
            errors.append("Username is required.")
        elif username != user.username:
            try:
                User._meta.get_field("username").clean(username, None)
            except ValidationError as exc:
                errors.extend(exc.messages)
            if User.objects.filter(username__iexact=username).exclude(pk=user.pk).exists():
                errors.append("That username is already in use.")
        username_changed = bool(username and username != user.username)
        email_changed = bool(email and email != str(user.email or "").strip().lower())
        if email_changed:
            try:
                validate_email(email)
            except ValidationError as exc:
                errors.extend(exc.messages)
            if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                errors.append("That email address is already registered.")
        if errors:
            return render(request, "core/account_identity.html", {
                "username": username or user.username, "email": email or user.email,
                "email_verified": profile.email_verified,
                "password_required": user.has_usable_password(), "google_identity_linked": GoogleIdentity.objects.filter(user=user, provider="google").exists(), "errors": errors,
            })
        if username_changed:
            user.username = username
            user.save(update_fields=["username"])
            messages.success(request, "Your AlgoBot username has been updated.")
        if email_changed:
            email_sent = _send_verification(
                request, user, profile, recipient=email, purpose="change_email",
                extra_payload={"email": email},
            )
            if email_sent:
                messages.info(request, "A verification link was sent to your new email. Your current email remains active until verification.")
            else:
                messages.warning(request, "Your username was saved, but the email verification message could not be sent. Request a new link after checking email configuration.")
        elif not username_changed:
            messages.info(request, "No email change was requested.")
        return redirect("account_identity_page")
    return render(request, "core/account_identity.html", {
        "username": user.username, "email": user.email,
        "email_verified": profile.email_verified,
        "password_required": user.has_usable_password(),
        "google_identity_linked": GoogleIdentity.objects.filter(user=user, provider="google").exists(),
    })


def verify_email_page(request):
    raw_token = str(request.GET.get("token") or request.POST.get("token") or "")
    if raw_token:
        try:
            signed_payload = signing.loads(
                raw_token, salt="algobot-email-verification", max_age=24 * 60 * 60
            )
            signed_user_id = signed_payload.get("uid")
            purpose = signed_payload.get("purpose", "verify_email")
            pending_email = str(signed_payload.get("email") or "").strip().lower()
        except signing.BadSignature:
            signed_user_id = None
            purpose = "verify_email"
            pending_email = ""

        if purpose not in {"verify_email", "change_email"}:
            signed_user_id = None

        profile = UserProfile.objects.filter(
            user_id=signed_user_id,
            email_verification_token=_digest(raw_token),
        ).select_related("user").first() if signed_user_id else None
        valid_for_purpose = bool(
            profile
            and profile.user.is_active
            and (
                (purpose == "verify_email" and profile.user.email and not profile.email_verified)
                or (purpose == "change_email" and pending_email)
            )
        )
        if not valid_for_purpose:
            messages.error(request, "That verification link is invalid, expired, or has already been used.")
            return _render(request, "verify_email", invalid=True)

        # Do not consume a verification token on GET: mail-security scanners
        # commonly prefetch links. Require an explicit CSRF-protected POST.
        if request.method == "GET":
            return _render(
                request, "verify_email", confirm_token=raw_token,
                confirm_purpose=purpose,
            )

        with transaction.atomic():
            profile = UserProfile.objects.select_for_update().filter(
                user_id=signed_user_id,
                email_verification_token=_digest(raw_token),
            ).select_related("user").first()
            if not profile or not profile.user.is_active:
                return _render(request, "verify_email", invalid=True)

            if purpose == "change_email":
                try:
                    validate_email(pending_email)
                except ValidationError:
                    profile = None
                if profile and User.objects.filter(email__iexact=pending_email).exclude(pk=profile.user_id).exists():
                    messages.error(request, "That email address is now in use. Request a new verification link for a different address.")
                    profile.email_verification_token = ""
                    profile.email_verification_token_created_at = None
                    profile.save(update_fields=["email_verification_token", "email_verification_token_created_at", "updated_at"])
                    return _render(request, "verify_email", invalid=True)
                if profile:
                    try:
                        # The nested savepoint converts a concurrent email-claim
                        # race into a safe response without breaking the outer
                        # token-consumption transaction.
                        with transaction.atomic():
                            profile.user.email = pending_email
                            profile.user.save(update_fields=["email"])
                    except IntegrityError:
                        profile.email_verification_token = ""
                        profile.email_verification_token_created_at = None
                        profile.save(update_fields=["email_verification_token", "email_verification_token_created_at", "updated_at"])
                        messages.error(request, "That email address is now in use. Request a new link for a different address.")
                        return _render(request, "verify_email", invalid=True)
                    profile.email_verified = True
                    profile.email_verified_at = timezone.now()
                    profile.email_verification_token = ""
                    profile.email_verification_token_created_at = None
                    profile.save(update_fields=["email_verified", "email_verified_at", "email_verification_token", "email_verification_token_created_at", "updated_at"])
                    messages.success(request, "Your new email address has been verified and saved.")
                    return redirect("account_identity_page")
            elif purpose == "verify_email" and profile.user.email and not profile.email_verified:
                profile.email_verified = True
                profile.email_verified_at = timezone.now()
                profile.email_verification_token = ""
                profile.email_verification_token_created_at = None
                profile.save(update_fields=["email_verified", "email_verified_at", "email_verification_token", "email_verification_token_created_at", "updated_at"])
                messages.success(request, "Your email address has been verified.")
                return redirect("login_page")

        messages.error(request, "That verification link is invalid, expired, or has already been used.")
        return _render(request, "verify_email", invalid=True)

    if request.method == "POST":
        email = str(request.session.get(PENDING_VERIFICATION_EMAIL_SESSION_KEY) or request.POST.get("email") or "").strip().lower()
        email_allowed = allow_auth_attempt(request, "verification-resend", email, limit=3, window=3600)
        ip_allowed = allow_auth_attempt(request, "verification-resend-ip", "", limit=10, window=3600)
        rate_allowed = email_allowed and ip_allowed
        matches = User.objects.filter(email__iexact=email, is_active=True) if rate_allowed else User.objects.none()
        if matches.count() == 1:
            user = matches.first()
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if not profile.email_verified:
                created_at = profile.email_verification_token_created_at
                remaining = max(0, int((created_at + VERIFICATION_RESEND_COOLDOWN - timezone.now()).total_seconds())) if created_at else 0
                if remaining:
                    request.session["verification_resend_wait_seconds"] = remaining
                    messages.info(request, "Please wait for the resend timer to finish before requesting another verification email.")
                else:
                    sent = _send_verification(request, user, profile)
                    request.session["verification_resend_wait_seconds"] = VERIFICATION_RESEND_COOLDOWN.seconds if sent else 0
                    logger.info("verification_resend_attempted outcome=%s", "provider_accepted" if sent else "provider_failed")
            else:
                logger.info("verification_resend_skipped reason=already_verified")
        else:
            logger.info("verification_resend_skipped reason=no_matching_active_account")
        request.session[PENDING_VERIFICATION_EMAIL_SESSION_KEY] = email
        messages.info(request, "If an unverified account matches that email, a verification link will be sent.")
        return redirect("verify_email_page")
    pending_email = str(request.session.get(PENDING_VERIFICATION_EMAIL_SESSION_KEY) or "").strip().lower()
    cooldown_seconds = int(request.session.pop("verification_resend_wait_seconds", 0) or 0)
    if pending_email:
        pending_user = User.objects.filter(email__iexact=pending_email, is_active=True).first()
        profile = UserProfile.objects.filter(user=pending_user).first() if pending_user else None
        if profile and profile.email_verification_token_created_at and not profile.email_verified:
            cooldown_seconds = max(cooldown_seconds, max(0, int((profile.email_verification_token_created_at + VERIFICATION_RESEND_COOLDOWN - timezone.now()).total_seconds())))
    return _render(request, "verify_email", verification_email=pending_email, cooldown_seconds=cooldown_seconds)



def unlink_google_identity(request):
    """Unlink Google only after local password proof, preserving a login method."""
    from django.views.decorators.http import require_POST

    if request.method != "POST":
        return render(request, "core/account_identity.html", status=405)
    user = request.user
    identity = GoogleIdentity.objects.filter(user=user, provider="google").first()
    if identity is None:
        messages.info(request, "No Google identity is linked to this account.")
        return redirect("account_identity_page")
    if not user.has_usable_password():
        messages.error(request, "Set and verify a local password before unlinking Google so you do not lose access.")
        return redirect("account_identity_page")
    if not user.check_password(request.POST.get("current_password") or ""):
        messages.error(request, "Enter your current AlgoBot password to unlink Google.")
        return redirect("account_identity_page")
    identity.delete()
    messages.success(request, "Google sign-in has been unlinked from your AlgoBot account.")
    return redirect("account_identity_page")



def two_factor_challenge_page(request):
    """Complete the second factor after a provider-authenticated sign-in."""
    pending_user_id = request.session.get("algobot_pending_2fa_user_id")
    if not pending_user_id:
        messages.error(request, "Start sign-in again to verify your account.")
        return redirect("login_page")
    user = User.objects.filter(pk=pending_user_id, is_active=True).first()
    profile = UserProfile.objects.filter(user=user).first() if user else None
    if not user or not profile or not profile.two_factor_enabled:
        request.session.pop("algobot_pending_2fa_user_id", None)
        messages.error(request, "That sign-in challenge is no longer valid. Please sign in again.")
        return redirect("login_page")
    if request.method == "POST":
        from core.services.two_factor_service import verify_user_code
        code = request.POST.get("two_factor_code") or ""
        allowed = allow_auth_attempt(request, "two-factor-challenge", str(user.pk), limit=10, window=900)
        ip_allowed = allow_auth_attempt(request, "two-factor-challenge-ip", "", limit=30, window=900)
        if not allowed or not ip_allowed:
            return render(request, "core/two_factor_challenge.html", {
                "error": "Too many verification attempts. Wait before trying again."
            }, status=429)
        if not verify_user_code(profile, code, consume_recovery=True):
            return render(request, "core/two_factor_challenge.html", {
                "error": "The authenticator or recovery code is invalid."
            }, status=400)
        request.session.pop("algobot_pending_2fa_user_id", None)
        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        request.session["algobot_mfa_verified_user_id"] = user.pk
        UserProfile.objects.filter(user=user).update(last_login_at=timezone.now())
        request.session.pop("broker_onboarding_next", None)
        google_destination = request.session.pop("algobot_google_post_2fa_destination", None)
        if google_destination == "profile":
            request.session["google_profile_completion_pending"] = True
            return redirect("profile_completion_page")
        if google_destination == "dashboard":
            request.session["google_existing_login_dashboard"] = True
            return redirect("dashboard_page")
        return redirect("broker_marketplace_page")
    return render(request, "core/two_factor_challenge.html")
