"""User-scoped browser session inventory and revocation endpoints."""
import hashlib
import logging

from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.utils import timezone
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def _sessions_for(user):
    """Return active DB-backed sessions belonging to user, without exposing session keys."""
    active = []
    now = timezone.now()
    for session in Session.objects.filter(expire_date__gt=now).order_by("-expire_date")[:2000].iterator():
        try:
            data = session.get_decoded()
        except Exception:
            continue
        if str(data.get("_auth_user_id", "")) == str(user.pk):
            active.append(session)
    return active


def _fingerprint(session_key):
    # Raw Django session IDs are bearer credentials and must never reach the UI.
    return hashlib.sha256(str(session_key).encode("utf-8")).hexdigest()


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def session_inventory(request):
    current_key = request.session.session_key
    sessions = _sessions_for(request.user)
    return Response({
        "sessions": [{
            "id": _fingerprint(item.session_key),
            "current": bool(current_key and item.session_key == current_key),
            "expires_at": item.expire_date,
            "device": "Current browser" if current_key and item.session_key == current_key else "Other signed-in browser",
        } for item in sessions],
        "revocation_supported": True,
    })


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def revoke_session(request, fingerprint):
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        return Response({"detail": "Invalid session reference."}, status=400)
    current_key = request.session.session_key
    for session in _sessions_for(request.user):
        if _fingerprint(session.session_key) != fingerprint:
            continue
        if current_key and session.session_key == current_key:
            return Response({"detail": "Use Sign out to end the current session."}, status=400)
        session.delete()
        logger.info("user_session_revoked user_id=%s", request.user.pk)
        return Response({"revoked": True, "session": fingerprint})
    return Response({"detail": "Session not found or already expired."}, status=404)
