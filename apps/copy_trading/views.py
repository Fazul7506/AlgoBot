import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db import models
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from .models import CopyProvider, CopyFollower, CopySubscription, CopyTrade
from .services import CopyTradingEngine, ProviderDiscoveryService


def _tenant(request):
    tenant = getattr(request.user, "tenant", None)
    if tenant is not None:
        return tenant
    try:
        from apps.tenants.models import Tenant
        return Tenant.objects.filter(owner=request.user).first()
    except Exception:
        return None


def _provider_dict(p):
    return {
        "id": p.id,
        "name": p.name,
        "slug": p.slug,
        "status": p.status,
        "strategy": p.strategy,
        "description": p.description,
        "risk_score": float(p.risk_score or 0),
        "return_pct": float(p.return_pct or 0),
        "win_rate": float(p.win_rate or 0),
        "max_drawdown_pct": float(p.max_drawdown_pct or 0),
        "followers": p.followers_count,
        "min_allocation": str(p.min_allocation),
        "max_allocation": str(p.max_allocation),
    }


def _follower_dict(f):
    sub = getattr(f, "subscription", None)
    return {
        "id": f.id,
        "status": f.status,
        "allocation": str(f.allocation),
        "allocation_mode": f.allocation_mode,
        "max_daily_loss_pct": float(f.max_daily_loss_pct),
        "max_drawdown_pct": float(f.max_drawdown_pct),
        "max_trade_stake": str(f.max_trade_stake),
        "max_concurrent_trades": f.max_concurrent_trades,
        "pause_on_loss_streak": f.pause_on_loss_streak,
        "copy_multiplier": float(f.copy_multiplier),
        "provider": _provider_dict(f.provider),
        "subscription": {
            "active": bool(sub and sub.status == "active"),
            "started_at": sub.started_at.isoformat() if sub and sub.started_at else None,
        },
    }


@login_required
@require_http_methods(["GET"])
def dashboard(request):
    tenant = _tenant(request)
    providers = ProviderDiscoveryService().discover(tenant=tenant)
    follower = CopyFollower.objects.filter(user=request.user, tenant=tenant).select_related("provider").prefetch_related("subscription").first() if tenant else None
    trades = CopyTrade.objects.filter(follower=follower).order_by("-opened_at")[:50] if follower else []
    return JsonResponse({
        "timestamp": timezone.now().isoformat(),
        "providers": [_provider_dict(p) for p in providers],
        "follower": _follower_dict(follower) if follower else None,
        "trades": [{
            "id": t.id, "symbol": t.symbol, "direction": t.direction,
            "stake": str(t.stake), "source_stake": str(t.source_stake),
            "status": t.status, "profit": str(t.profit),
            "opened_at": t.opened_at.isoformat() if t.opened_at else None,
            "closed_at": t.closed_at.isoformat() if t.closed_at else None,
            "rejection_reason": t.rejection_reason,
        } for t in trades],
    })


@login_required
@require_http_methods(["POST"])
def subscribe(request):
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    tenant = _tenant(request)
    try:
        provider_qs = CopyProvider.objects.filter(id=int(data["provider_id"]), status="active")
        if tenant is not None:
            provider_qs = provider_qs.filter(
                models.Q(tenant=tenant) | models.Q(tenant__isnull=True)
            )
        provider = provider_qs.get()
    except (KeyError, ValueError, TypeError, CopyProvider.DoesNotExist):
        return JsonResponse({"error": "Active provider not found."}, status=400)
    if tenant is None:
        return JsonResponse({"error": "A tenant/workspace is required for copy trading."}, status=400)

    try:
        allocation = Decimal(str(data.get("allocation", "0")))
        multiplier = Decimal(str(data.get("copy_multiplier", "1")))
    except (InvalidOperation, ValueError, TypeError):
        return JsonResponse({"error": "Invalid allocation or multiplier."}, status=400)

    if allocation < provider.min_allocation or allocation > provider.max_allocation:
        return JsonResponse({"error": "Allocation is outside the provider limits."}, status=400)
    if multiplier <= 0:
        return JsonResponse({"error": "Copy multiplier must be greater than zero."}, status=400)

    allocation_mode = data.get("allocation_mode", "fixed")
    if allocation_mode not in {"fixed", "proportional"}:
        return JsonResponse({"error": "Invalid allocation mode."}, status=400)

    follower, _ = CopyFollower.objects.get_or_create(
        user=request.user, tenant=tenant, provider=provider,
        defaults={"allocation": allocation},
    )
    follower.allocation = allocation
    follower.allocation_mode = allocation_mode
    follower.max_daily_loss_pct = Decimal(str(data.get("max_daily_loss_pct", follower.max_daily_loss_pct)))
    follower.max_drawdown_pct = Decimal(str(data.get("max_drawdown_pct", follower.max_drawdown_pct)))
    follower.max_trade_stake = Decimal(str(data.get("max_trade_stake", follower.max_trade_stake)))
    follower.max_concurrent_trades = int(data.get("max_concurrent_trades", follower.max_concurrent_trades))
    follower.pause_on_loss_streak = int(data.get("pause_on_loss_streak", follower.pause_on_loss_streak))
    follower.copy_multiplier = multiplier
    follower.status = "active"
    follower.save()

    CopySubscription.objects.update_or_create(
        follower=follower,
        defaults={"status": "active", "started_at": timezone.now()},
    )
    return JsonResponse({"follower": _follower_dict(follower)}, status=201)


@login_required
@require_http_methods(["POST"])
def pause(request):
    tenant = _tenant(request)
    follower = CopyFollower.objects.filter(user=request.user, tenant=tenant).first() if tenant else None
    if not follower:
        return JsonResponse({"error": "No copy-trading subscription found."}, status=404)
    follower.status = "paused"
    follower.save(update_fields=["status"])
    CopySubscription.objects.filter(follower=follower).update(status="paused")
    return JsonResponse({"status": "paused"})


@login_required
@require_http_methods(["POST"])
def resume(request):
    tenant = _tenant(request)
    follower = CopyFollower.objects.filter(user=request.user, tenant=tenant).first() if tenant else None
    if not follower:
        return JsonResponse({"error": "No copy-trading subscription found."}, status=404)
    follower.status = "active"
    follower.save(update_fields=["status"])
    CopySubscription.objects.filter(follower=follower).update(status="active")
    return JsonResponse({"status": "active"})


@login_required
@require_http_methods(["POST"])
def stop(request):
    tenant = _tenant(request)
    follower = CopyFollower.objects.filter(user=request.user, tenant=tenant).first() if tenant else None
    if not follower:
        return JsonResponse({"error": "No copy-trading subscription found."}, status=404)
    follower.status = "stopped"
    follower.save(update_fields=["status"])
    CopySubscription.objects.filter(follower=follower).update(status="cancelled")
    return JsonResponse({"status": "stopped"})


@login_required
@require_http_methods(["POST"])
def risk_settings(request):
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)
    tenant = _tenant(request)
    follower = CopyFollower.objects.filter(user=request.user, tenant=tenant).first() if tenant else None
    if not follower:
        return JsonResponse({"error": "No copy-trading subscription found."}, status=404)
    try:
        follower.max_daily_loss_pct = Decimal(str(data.get("max_daily_loss_pct", follower.max_daily_loss_pct)))
        follower.max_drawdown_pct = Decimal(str(data.get("max_drawdown_pct", follower.max_drawdown_pct)))
        follower.max_trade_stake = Decimal(str(data.get("max_trade_stake", follower.max_trade_stake)))
        follower.max_concurrent_trades = int(data.get("max_concurrent_trades", follower.max_concurrent_trades))
        follower.pause_on_loss_streak = int(data.get("pause_on_loss_streak", follower.pause_on_loss_streak))
        follower.copy_multiplier = Decimal(str(data.get("copy_multiplier", follower.copy_multiplier)))
        if follower.copy_multiplier <= 0:
            return JsonResponse({"error": "Copy multiplier must be greater than zero."}, status=400)
    except (InvalidOperation, ValueError, TypeError):
        return JsonResponse({"error": "Invalid risk settings."}, status=400)
    follower.save()
    return JsonResponse({"follower": _follower_dict(follower)})


@login_required
@require_http_methods(["POST"])
def test_copy(request):
    tenant = _tenant(request)
    follower = CopyFollower.objects.filter(user=request.user, tenant=tenant).first() if tenant else None
    if not follower:
        return JsonResponse({"error": "Subscribe to a provider first."}, status=400)
    result = CopyTradingEngine().simulate_signal(follower=follower, dry_run=True)
    return JsonResponse({"dry_run": True, "result": result})
