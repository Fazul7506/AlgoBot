import logging
import secrets
import json
import requests
from urllib.parse import urlparse

from django.conf import settings
from django.shortcuts import redirect, render
from django.http import HttpResponse
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.utils.crypto import get_random_string
from rest_framework_simplejwt.tokens import RefreshToken

from apps.brokers.models import Broker
from trading.models import DerivAccount
from core.services.oauth_service import DerivOAuthService

oauth_logger = logging.getLogger("oauth")


def _ensure_user_defaults(user):
    """Create OAuth-created users' required related records idempotently."""
    from core.models import UserProfile, Subscription, BotSettings

    UserProfile.objects.get_or_create(user=user)
    Subscription.objects.get_or_create(user=user)
    BotSettings.objects.get_or_create(user=user)
