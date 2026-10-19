"""Authenticated browser views for the user's own AlgoBot profile."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

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
        if len(phone) > 20:
            errors.append("Phone number must be 20 characters or fewer.")
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
            profile.save(update_fields=["country", "timezone", "phone", "bio", "updated_at"])
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
        "profile_initials": (request.user.first_name[:1] + request.user.last_name[:1]).upper()
            if request.user.first_name and request.user.last_name
            else request.user.username[:2].upper(),
    })
