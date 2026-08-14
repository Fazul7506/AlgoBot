from decimal import Decimal, InvalidOperation

from .models import (
    CopyFollower,
    CopyProvider,
    CopySubscription,
    CopyTrade,
)


class ProviderDiscoveryService:
    def discover(self, tenant=None):
        qs = CopyProvider.objects.filter(status="active")
        if tenant is not None:
            qs = qs.filter(tenant=tenant) | qs.filter(tenant__isnull=True)
        return qs.order_by("-return_pct", "-followers_count", "name").distinct()


class CopyRiskEngine:
    """Enforces follower-side limits before a copied trade is authorized."""

    def authorize(self, follower, source_stake, concurrent_trades=0):
        if follower.status != "active":
            return False, "Follower is not active."

        try:
            source = Decimal(str(source_stake))
        except (InvalidOperation, ValueError, TypeError):
            return False, "Invalid source stake."

        if source <= 0:
            return False, "Source stake must be positive."

        stake = source * follower.copy_multiplier

        if stake > follower.max_trade_stake:
            return False, "Copied stake exceeds follower max trade stake."

        if concurrent_trades >= follower.max_concurrent_trades:
            return False, "Maximum concurrent copied trades reached."

        return True, ""


class CopyTradingEngine:
    def start(self, follower):
        follower.status = "active"
        follower.save(update_fields=["status"])
        CopySubscription.objects.update_or_create(
            follower=follower,
            defaults={"status": "active"},
        )
        return follower

    def stop(self, subject):
        """Stop either a CopyFollower or a legacy StrategySubscription.

        The codebase currently exposes both the Phase-17 follower model and the
        older strategy-subscription model. Keep the lifecycle operation
        backwards-compatible while making the authoritative state explicit.
        """
        from .models import CopyFollower, StrategySubscription

        if isinstance(subject, StrategySubscription):
            subject.status = "paused"
            subject.save(update_fields=["status"])
            return subject

        if isinstance(subject, CopyFollower):
            subject.status = "stopped"
            subject.save(update_fields=["status"])
            CopySubscription.objects.filter(follower=subject).update(status="cancelled")
            return subject

        raise TypeError(
            "CopyTradingEngine.stop() expects CopyFollower or StrategySubscription"
        )

    def simulate_signal(self, follower, dry_run=True):
        provider = follower.provider
        source_stake = Decimal("1")
        proposed_stake = source_stake * follower.copy_multiplier
        allowed, reason = CopyRiskEngine().authorize(
            follower,
            source_stake,
            concurrent_trades=0,
        )

        return {
            "provider_id": provider.id,
            "provider_name": provider.name,
            "follower_id": follower.id,
            "source_stake": str(source_stake),
            "proposed_stake": str(proposed_stake),
            "authorized": allowed,
            "rejection_reason": reason,
            "dry_run": dry_run,
            "status": "authorized" if allowed else "rejected",
        }

    def execute_copy(self, follower, symbol, direction, source_stake, provider_trade=""):
        allowed, reason = CopyRiskEngine().authorize(follower, source_stake)
        stake = Decimal(str(source_stake)) * follower.copy_multiplier
        trade = CopyTrade.objects.create(
            follower=follower,
            provider_trade=str(provider_trade)[:120],
            symbol=str(symbol)[:80],
            direction=str(direction)[:20],
            stake=stake if allowed else Decimal("0"),
            source_stake=Decimal(str(source_stake)),
            status="pending" if allowed else "rejected",
            rejection_reason="" if allowed else reason,
        )
        return trade


class SignalEngine:
    def publish(self, strategy, payload):
        return {
            "strategy_id": strategy.id,
            "signal": payload,
            "status": "published",
        }


class MirrorExecutionService:
    def mirror(self, provider_trade, subscription, allocation=1, multiplier=1):
        from .models import TradeMirror

        return TradeMirror.objects.create(
            provider_trade=str(provider_trade),
            allocation=Decimal(str(allocation)),
            multiplier=Decimal(str(multiplier)),
            status="mirrored",
        )


class PortfolioMirrorService:
    pass


class RiskScalingService:
    def scale(self, stake, multiplier=1, max_exposure=None):
        value = Decimal(str(stake)) * Decimal(str(multiplier))
        if max_exposure is not None:
            value = min(value, Decimal(str(max_exposure)))
        return value


class ProviderService:
    pass


class FollowerService:
    pass


class SubscriptionService:
    pass


class MarketplaceService:
    pass


class RankingService:
    pass


class AnalyticsService:
    def roi(self, profit, capital):
        return Decimal("0") if not capital else Decimal(str(profit)) / Decimal(str(capital))


class RevenueService:
    pass


class CommunityService:
    pass


class ReviewService:
    pass


class VerificationService:
    pass
