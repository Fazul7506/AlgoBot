import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core.models import BotSettings, UserProfile


@login_required
@require_http_methods(["GET", "PATCH"])
def account_settings_api(request):
    """Read/write non-secret account and trading preferences for the signed-in user.

    Secrets and broker credentials are intentionally excluded. Broker connection
    state remains owned by the broker APIs and is not writable from this endpoint.
    """
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
                "two_factor_enabled": profile.two_factor_enabled,
            },
            "trading": {
                "default_strategy": bot.default_strategy,
                "max_daily_loss_pct": bot.max_daily_loss_pct,
                "risk_per_trade_pct": bot.risk_per_trade_pct,
                "max_concurrent_trades": bot.max_concurrent_trades,
                "min_win_rate": bot.min_win_rate,
                "is_paper_trading": bot.is_paper_trading,
            },
        })

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON payload."}, status=400)

    profile_data = payload.get("profile", {})
    trading_data = payload.get("trading", {})

    allowed_profile = {
        "country", "timezone", "phone", "bio", "notifications_enabled",
        "email_notifications_enabled", "telegram_notifications_enabled",
    }
    allowed_trading = {
        "default_strategy", "max_daily_loss_pct", "risk_per_trade_pct",
        "max_concurrent_trades", "min_win_rate", "is_paper_trading",
    }

    for field in allowed_profile:
        if field in profile_data:
            setattr(profile, field, profile_data[field])
    for field in allowed_trading:
        if field in trading_data:
            setattr(bot, field, trading_data[field])

    try:
        if bot.max_daily_loss_pct < 0 or bot.max_daily_loss_pct > 1:
            raise ValueError("max_daily_loss_pct must be between 0 and 1")
        if bot.risk_per_trade_pct < 0 or bot.risk_per_trade_pct > 1:
            raise ValueError("risk_per_trade_pct must be between 0 and 1")
        if bot.min_win_rate < 0 or bot.min_win_rate > 1:
            raise ValueError("min_win_rate must be between 0 and 1")
        if bot.max_concurrent_trades < 1:
            raise ValueError("max_concurrent_trades must be at least 1")
    except (TypeError, ValueError) as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    profile.save()
    bot.save()
    return JsonResponse({"ok": True, "message": "Settings saved."})
