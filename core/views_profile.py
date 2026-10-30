"""Authenticated browser views for the user's own AlgoBot profile."""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.http import HttpResponse, Http404
from django.views.decorators.http import require_GET
import io
from django.views.decorators.http import require_http_methods
from zoneinfo import available_timezones
from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.db import DatabaseError, transaction

from core.models import UserProfile

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET", "POST"])
def profile_page(request):
    """Render and persist non-secret personal profile fields for the current user."""
    profile = UserProfile.objects.filter(user=request.user).first()
    if profile is None:
        profile = UserProfile(user=request.user)
    if request.method == "POST":
        first_name = str(request.POST.get("first_name") or "").strip()
        last_name = str(request.POST.get("last_name") or "").strip()
        country = str(request.POST.get("country") or "").strip()
        timezone_name = str(request.POST.get("timezone") or "UTC").strip() or "UTC"
        phone = str(request.POST.get("phone") or "").strip()
        bio = str(request.POST.get("bio") or "").strip()
        avatar_file = request.FILES.get("profile_picture")
        picture_data = None
        picture_content_type = ""

        errors = []
        if not first_name:
            errors.append("First name is required.")
        if not last_name:
            errors.append("Last name is required.")
        if len(first_name) > 150 or len(last_name) > 150:
            errors.append("Names must be 150 characters or fewer.")
        if len(country) > 100:
            errors.append("Country must be 100 characters or fewer.")
        if len(timezone_name) > 100:
            errors.append("Timezone must be 100 characters or fewer.")
        if len(phone) > 32:
            errors.append("Phone number must be 32 characters or fewer.")
        if timezone_name not in available_timezones():
            errors.append("Choose a valid time zone.")
        if avatar_file:
            if avatar_file.size > 5 * 1024 * 1024:
                errors.append("Profile picture must be 5 MB or smaller.")
            else:
                try:
                    image = Image.open(avatar_file)
                    image_format = image.format
                    if image_format not in {"JPEG", "PNG", "WEBP", "GIF"}:
                        errors.append("Profile picture must be a JPEG, PNG, WEBP, or GIF image.")
                    elif image.width * image.height > 25_000_000:
                        errors.append("Profile picture dimensions must not exceed 25 megapixels.")
                    else:
                        image.verify()
                        avatar_file.seek(0)
                        image = Image.open(avatar_file)
                        image.load()
                        has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
                        normalized = image.convert("RGBA" if has_alpha else "RGB")
                        normalized.thumbnail((512, 512), Image.Resampling.LANCZOS)
                        buffer = io.BytesIO()
                        normalized.save(buffer, format="WEBP", quality=85, method=6)
                        picture_data = buffer.getvalue()
                        picture_content_type = "image/webp"
                    avatar_file.seek(0)
                except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
                    errors.append("Upload a valid image file (JPEG, PNG, WEBP, or GIF).")
                    avatar_file.seek(0)
        if len(bio) > 5000:
            errors.append("Bio must be 5,000 characters or fewer.")

        if errors:
            for error in errors:
                messages.error(request, error)
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return HttpResponse(status=422)
        else:
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            request.user.first_name = first_name
            request.user.last_name = last_name
            profile.country = country
            profile.timezone = timezone_name
            profile.phone = phone
            profile.bio = bio
            if picture_data is not None:
                # Persist the normalized, cropped avatar in the profile row so it
                # remains available after refresh even without external object storage.
                profile.profile_picture_data = picture_data
                profile.profile_picture_content_type = picture_content_type
                profile.avatar_url = ""

            # Keep the auth identity and extended profile in one transaction. A
            # failed profile/avatar write must not leave half of the submitted form
            # persisted.
            try:
                with transaction.atomic():
                    request.user.save(update_fields=["first_name", "last_name"])
                    # The profile row is normally created by the user signal, but
                    # support older/imported accounts that do not have one yet.
                    if profile.pk is None:
                        profile.save()
                    profile.save(update_fields=[
                        "country", "timezone", "phone", "bio",
                        "avatar_url", "profile_picture_data",
                        "profile_picture_content_type", "updated_at",
                    ])
            except DatabaseError:
                # Roll back and refresh both in-memory objects so a failed write
                # cannot leak partially updated identity/avatar state into rendering.
                logger.exception("Failed to persist profile changes for user_id=%s", request.user.pk)
                request.user.refresh_from_db()
                profile = UserProfile.objects.filter(user=request.user).first() or UserProfile(user=request.user)
                messages.error(
                    request,
                    "We couldn't save your profile because of a temporary storage problem. "
                    "Your changes were not applied; please try again.",
                )
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return HttpResponse(status=503)
            else:
                messages.success(request, "Your profile has been saved.")
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return HttpResponse(status=204)
                return redirect("profile_page")

    # Completion is derived from persisted profile fields, not a hardcoded score.
    completion_fields = (
        request.user.first_name,
        request.user.last_name,
        request.user.email,
        profile.country,
        profile.timezone,
        profile.phone,
        bool(profile.profile_picture_data or profile.avatar_url),
    )
    profile_completion_percent = round(100 * sum(bool(value and str(value).strip()) for value in completion_fields) / len(completion_fields))

    # Show only genuine, user-scoped authentication audit records. The audit
    # model deliberately stores no raw credentials and this view omits IP data.
    from apps.observability.models import AuditEvent
    recent_activity = list(
        AuditEvent.objects.filter(actor_id=request.user.pk, resource_type="Authentication")
        .order_by("-created_at")[:5]
    )

    return render(request, "core/profile.html", {
        "profile": profile,
        "profile_completion_percent": profile_completion_percent,
        "recent_activity": recent_activity,
        "first_name": request.POST.get("first_name", request.user.first_name),
        "last_name": request.POST.get("last_name", request.user.last_name),
        "country": request.POST.get("country", profile.country),
        "timezone_value": request.POST.get("timezone", profile.timezone or "UTC"),
        "phone": request.POST.get("phone", profile.phone),
        "bio": request.POST.get("bio", profile.bio),
        "timezone_choices": sorted(available_timezones()),
        "profile_initials": (request.user.first_name[:1] + request.user.last_name[:1]).upper()
            if request.user.first_name and request.user.last_name
            else request.user.username[:2].upper(),
    })



@login_required
@require_GET
def profile_picture(request):
    """Serve the authenticated user's persistent profile photo or a legacy avatar."""
    from urllib.parse import urlparse

    profile = UserProfile.objects.filter(user=request.user).only(
        "profile_picture_data", "profile_picture_content_type", "avatar_url"
    ).first()
    if profile and profile.profile_picture_data:
        content_type = profile.profile_picture_content_type or "image/webp"
        if content_type not in {"image/webp", "image/jpeg", "image/png", "image/gif"}:
            raise Http404("Profile picture content type is invalid.")
        response = HttpResponse(bytes(profile.profile_picture_data), content_type=content_type)
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, max-age=300"
        return response

    # Preserve compatibility with legacy Cloudinary avatars already saved.
    url = str(getattr(profile, "avatar_url", "") or "").strip() if profile else ""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    trusted_avatar_host = (
        hostname == "res.cloudinary.com"
        or hostname == "googleusercontent.com"
        or hostname.endswith(".googleusercontent.com")
    )
    if parsed.scheme != "https" or not trusted_avatar_host:
        raise Http404("Profile picture not found.")
    response = redirect(url)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, max-age=300"
    return response
