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
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
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


def _send_account_email(subject, body, email):
    try:
        # Reuse AlgoBot's configured transactional delivery path (Brevo when
        # configured, Django email backend otherwise) for auth/security mail.
        from apps.notifications.services import send_transactional_email
        send_transactional_email(
            recipient=email, subject=subject, message=body,
            category="authentication",
        )
        return True
    except Exception:
        logger.exception("account_email_delivery_failed")
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
        body = "To change your AlgoBot email address, confirm ownership of the new address here:\n\n" + link + "\n\nYour current email remains unchanged until you verify this link."
    else:
        subject = "Verify your AlgoBot email address"
        body = "To verify your AlgoBot email address, open this link:\n\n" + link + "\n\nIf you did not create this account, you can ignore this message."
    return _send_account_email(subject, body, email)


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
            messages.error(request, "The username/email or password is incorrect.")
            return _render(request, "login", identifier=identifier)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if not profile.email_verified:
            messages.info(request, "Please verify your email before signing in. You can request a fresh verification link below.")
            return redirect("verify_email_page")
        auth_login(request, user)
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
        email = str(request.POST.get("email") or "").strip().lower()
        password = request.POST.get("password") or ""
        confirm = request.POST.get("password_confirm") or ""
        errors = []
        if not username or not email or not password:
            errors.append("Username, email, and password are required.")
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
        candidate = User(username=username, email=email)
        if password:
            try:
                validate_password(password, user=candidate)
            except ValidationError as exc:
                errors.extend(exc.messages)
        if errors:
            return _render(request, "register", errors=errors, username=username, email=email)
        try:
            with transaction.atomic():
                user = User.objects.create_user(username=username, email=email, password=password)
                profile, _ = UserProfile.objects.get_or_create(user=user)
                Subscription.objects.get_or_create(user=user)
                BotSettings.objects.get_or_create(user=user)
            email_sent = _send_verification(request, user, profile)
        except IntegrityError:
            return _render(
                request, "register",
                errors=["An account could not be created with those details. If you already have an account, sign in or use account recovery."],
                username=username, email=email,
            )
        if email_sent:
            messages.success(request, "Your account was created. Verify your email before signing in.")
        else:
            messages.warning(request, "Your account was created, but the verification email could not be sent. Use Verify email to request another.")
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
        email = str(request.POST.get("email") or "").strip().lower()
        email_allowed = allow_auth_attempt(request, "verification-resend", email, limit=3, window=3600)
        ip_allowed = allow_auth_attempt(request, "verification-resend-ip", "", limit=10, window=3600)
        rate_allowed = email_allowed and ip_allowed
        matches = User.objects.filter(email__iexact=email, is_active=True) if rate_allowed else User.objects.none()
        if matches.count() == 1:
            user = matches.first()
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if not profile.email_verified:
                _send_verification(request, user, profile)
        messages.info(request, "If an unverified account matches that email, a verification link will be sent.")
        return redirect("verify_email_page")
    return _render(request, "verify_email")



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
