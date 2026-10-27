"""Authoritative profile-completion policy shared by authentication and middleware."""
from core.models import UserProfile


def profile_is_complete(user):
    """Evaluate persisted required profile data; never trust session flags."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not str(user.first_name or "").strip() or not str(user.last_name or "").strip():
        return False
    try:
        profile = UserProfile.objects.get(user_id=user.pk)
    except UserProfile.DoesNotExist:
        return False
    return bool(profile.terms_accepted_at)
