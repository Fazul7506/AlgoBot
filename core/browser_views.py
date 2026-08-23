"""HTML-only browser actions kept separate from DRF API views."""

from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.shortcuts import redirect
from django.views.decorators.http import require_POST


@require_POST
def browser_logout(request):
    """End the browser session, show a UI notification, and redirect to the public UI."""
    auth_logout(request)
    messages.success(request, "You have been logged out securely.")
    return redirect("home")
