"""Authenticated browser views for the user's own AlgoBot profile."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.http import HttpResponse, Http404
from django.views.decorators.http import require_GET
import io
from django.views.decorators.http import require_http_methods
from zoneinfo import available_timezones
from PIL import Image, UnidentifiedImageError

from core.models import UserProfile


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
        else:
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            request.user.first_name = first_name
            request.user.last_name = last_name
            request.user.save(update_fields=["first_name", "last_name"])
            profile.country = country
            profile.timezone = timezone_name
            profile.phone = phone
            profile.bio = bio
            if picture_data is not None:
                profile.profile_picture_data = picture_data
                profile.profile_picture_content_type = picture_content_type
            profile.save(update_fields=[
                "country", "timezone", "phone", "bio",
                "profile_picture_data", "profile_picture_content_type", "updated_at",
            ])
            messages.success(request, "Your profile has been saved.")
            return redirect("profile_page")

    return render(request, "core/profile.html", {
        "profile": profile,
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
    """Serve only the signed-in user's validated database-backed profile picture."""
    profile = UserProfile.objects.filter(user=request.user).only(
        "profile_picture_data", "profile_picture_content_type"
    ).first()
    if not profile or not profile.profile_picture_data:
        raise Http404("Profile picture not found.")
    content_type = profile.profile_picture_content_type
    if content_type not in {"image/webp", "image/jpeg", "image/png", "image/gif"}:
        raise Http404("Profile picture not found.")
    response = HttpResponse(bytes(profile.profile_picture_data), content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, max-age=300"
    return response
