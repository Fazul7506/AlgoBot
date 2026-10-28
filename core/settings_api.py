"""Authenticated settings API for non-secret account and trading preferences."""
import json
import math

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core.models import BotSettings, UserProfile


PROFILE_TEXT_LIMITS = {
    "country": 100,
    "timezone": 100,
    "phone": 20,
    "bio": 5000,
}
PROFILE_BOOLEAN_FIELDS = {
    "notifications_enabled",
    "email_notifications_enabled",
    "telegram_notifications_enabled",
}
ACCOUNT_PREFERENCE_DEFAULTS = {
    "theme": "dark",
    "density": "default",
    "accent": "cyan",
    "notification_categories": {
        "trade_alerts": True,
        "price_alerts": True,
        "market_news": True,
        "system_updates": True,
        "security_alerts": True,
    },
}
ACCOUNT_PREFERENCE_CHOICES = {
    "theme": {"light", "dark", "system"},
    "density": {"compact", "default", "comfortable"},
    "accent": {"cyan", "blue", "teal", "violet", "amber"},
}
ACCOUNT_NOTIFICATION_CATEGORIES = set(ACCOUNT_PREFERENCE_DEFAULTS["notification_categories"])


TRADING_FLOAT_LIMITS = {
    "max_daily_loss_pct": (0.0, 1.0),
    "risk_per_trade_pct": (0.0, 1.0),
    "min_win_rate": (0.0, 1.0),
}


@login_required
@require_http_methods(["GET", "PATCH"])
def account_settings_api(request):
    """Read/write settings for the current user without exposing credentials or tokens."""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    bot, _ = BotSettings.objects.get_or_create(user=request.user)

    if request.method == "GET":
        return JsonResponse({
            "user": {
                "username": request.user.username,
                "email": request.user.email,
                "first_name": request.user.first_name,
                "last_name": request.user.last_name,
            },
            "profile": {
                "country": profile.country,
                "timezone": profile.timezone,
                "phone": profile.phone,
                "bio": profile.bio,
                "notifications_enabled": profile.notifications_enabled,
                "email_notifications_enabled": profile.email_notifications_enabled,
                "telegram_notifications_enabled": profile.telegram_notifications_enabled,
                "account_preferences": {**ACCOUNT_PREFERENCE_DEFAULTS, **(profile.account_preferences or {}), "notification_categories": {**ACCOUNT_PREFERENCE_DEFAULTS["notification_categories"], **((profile.account_preferences or {}).get("notification_categories") or {})}},
            },
            "trading": {
                "default_strategy": bot.default_strategy,
                "max_daily_loss_pct": bot.max_daily_loss_pct,
                "risk_per_trade_pct": bot.risk_per_trade_pct,
                "max_concurrent_trades": bot.max_concurrent_trades,
                "min_win_rate": bot.min_win_rate,
            },
        })

    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Invalid JSON payload."}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"detail": "The request body must be an object."}, status=400)
    profile_data = payload.get("profile", {})
    trading_data = payload.get("trading", {})
    preferences_data = payload.get("preferences", {})
    if not isinstance(profile_data, dict) or not isinstance(trading_data, dict) or not isinstance(preferences_data, dict):
        return JsonResponse({"detail": "Profile, trading and preferences settings must be objects."}, status=400)

    profile_updates = {}
    for field, limit in PROFILE_TEXT_LIMITS.items():
        if field not in profile_data:
            continue
        value = profile_data[field]
        if not isinstance(value, str):
            return JsonResponse({"detail": f"{field} must be text."}, status=400)
        value = value.strip()
        if len(value) > limit:
            return JsonResponse({"detail": f"{field} must be {limit} characters or fewer."}, status=400)
        profile_updates[field] = value

    for field in PROFILE_BOOLEAN_FIELDS:
        if field not in profile_data:
            continue
        if not isinstance(profile_data[field], bool):
            return JsonResponse({"detail": f"{field} must be true or false."}, status=400)
        profile_updates[field] = profile_data[field]

    # Only explicitly supported preferences are accepted. Unknown values are rejected
    # so the UI cannot persist a setting that the application does not implement.
    preference_updates = {}
    current_preferences = {**ACCOUNT_PREFERENCE_DEFAULTS, **(profile.account_preferences or {})}
    current_preferences["notification_categories"] = {
        **ACCOUNT_PREFERENCE_DEFAULTS["notification_categories"],
        **((profile.account_preferences or {}).get("notification_categories") or {}),
    }
    for field, choices in ACCOUNT_PREFERENCE_CHOICES.items():
        if field not in preferences_data:
            continue
        value = preferences_data[field]
        if not isinstance(value, str) or value not in choices:
            return JsonResponse({"detail": f"Invalid value for preference: {field}."}, status=400)
        preference_updates[field] = value

    if "notification_categories" in preferences_data:
        categories = preferences_data["notification_categories"]
        if not isinstance(categories, dict) or set(categories) - ACCOUNT_NOTIFICATION_CATEGORIES:
            return JsonResponse({"detail": "notification_categories contains unsupported options."}, status=400)
        if any(not isinstance(value, bool) for value in categories.values()):
            return JsonResponse({"detail": "Notification category values must be true or false."}, status=400)
        # Security alerts are mandatory; never permit them to be disabled by a client.
        if categories.get("security_alerts") is False:
            return JsonResponse({"detail": "Security alerts cannot be disabled."}, status=400)
        preference_updates["notification_categories"] = {
            **current_preferences["notification_categories"],
            **categories,
        }

    trading_updates = {}
    if "default_strategy" in trading_data:
        value = trading_data["default_strategy"]
        if not isinstance(value, str) or len(value.strip()) > 100:
            return JsonResponse({"detail": "default_strategy must be text of 100 characters or fewer."}, status=400)
        trading_updates["default_strategy"] = value.strip() or "trend"

    for field, (minimum, maximum) in TRADING_FLOAT_LIMITS.items():
        if field not in trading_data:
            continue
        value = trading_data[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return JsonResponse({"detail": f"{field} must be a finite number."}, status=400)
        if value < minimum or value > maximum:
            return JsonResponse({"detail": f"{field} must be between {minimum} and {maximum}."}, status=400)
        trading_updates[field] = float(value)

    if "max_concurrent_trades" in trading_data:
        value = trading_data["max_concurrent_trades"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > 1000:
            return JsonResponse({"detail": "max_concurrent_trades must be a whole number between 1 and 1000."}, status=400)
        trading_updates["max_concurrent_trades"] = value

    # Validate every supplied field before writes, then persist only actual changes.
    # This avoids touching auto_now timestamps or issuing redundant UPDATEs when
    # a browser resubmits settings that are already current.
    changed_profile = {
        field: value for field, value in profile_updates.items()
        if getattr(profile, field) != value
    }
    changed_trading = {
        field: value for field, value in trading_updates.items()
        if getattr(bot, field) != value
    }

    updated_preferences = {**current_preferences, **preference_updates}
    changed_preferences = bool(preference_updates) and updated_preferences != current_preferences

    with transaction.atomic():
        for field, value in changed_profile.items():
            setattr(profile, field, value)
        for field, value in changed_trading.items():
            setattr(bot, field, value)
        if changed_profile:
            profile.save(update_fields=[*changed_profile.keys(), "updated_at"])
        if changed_trading:
            bot.save(update_fields=[*changed_trading.keys(), "updated_at"])
        if changed_preferences:
            profile.account_preferences = updated_preferences
            profile.save(update_fields=["account_preferences", "updated_at"])

    return JsonResponse({"ok": True, "message": "Settings saved.", "changed": bool(changed_profile or changed_trading or changed_preferences)})
