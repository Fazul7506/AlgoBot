from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.execution.models import Order
from apps.notifications.models import Notification
from apps.strategies.models import StrategySignal
from apps.trading.models import Position
from core.account_context import get_active_account


class DashboardViewSet(viewsets.ViewSet):
    """Canonical dashboard API backed by the authenticated user's active broker account."""

    permission_classes = [permissions.IsAuthenticated]

    @staticmethod
    def _limit(request, default=50, maximum=100):
        try:
            return min(max(int(request.GET.get("limit", default)), 1), maximum)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _orders_for_account(user, account):
        if not account:
            return Order.objects.none()
        return Order.objects.filter(user=user, broker_account=account)

    @staticmethod
    def _positions_for_account(user, account):
        if not account:
            return Position.objects.none()
        return Position.objects.filter(
            order__user=user,
            order__broker_account=account,
        )

    @staticmethod
    def _position_stats(positions):
        """Return persisted local trade P/L without manufacturing unavailable values."""
        aggregate = positions.aggregate(
            total=Count("id"),
            open_count=Count("id", filter=Q(status="open")),
            closed_count=Count("id", filter=Q(status="closed")),
            wins=Count("id", filter=Q(status="closed", profit_loss__gt=0)),
            losses=Count("id", filter=Q(status="closed", profit_loss__lt=0)),
            total_pnl=Sum("profit_loss"),
            realized_pnl=Sum("profit_loss", filter=Q(status="closed")),
            unrealized_pnl=Sum("profit_loss", filter=Q(status="open")),
        )
        closed_count = aggregate["closed_count"] or 0
        wins = aggregate["wins"] or 0
        losses = aggregate["losses"] or 0
        total_pnl = aggregate["total_pnl"] if aggregate["total_pnl"] is not None else Decimal("0")
        realized_pnl = aggregate["realized_pnl"] if aggregate["realized_pnl"] is not None else Decimal("0")
        unrealized_pnl = aggregate["unrealized_pnl"] if aggregate["unrealized_pnl"] is not None else Decimal("0")
        return {
            "total_trades": aggregate["total"] or 0,
            "open_trades": aggregate["open_count"] or 0,
            "closed_trades": closed_count,
            "wins": wins,
            "losses": losses,
            "win_rate": (Decimal(wins) / Decimal(closed_count) * Decimal("100")) if closed_count else Decimal("0"),
            "total_pnl": total_pnl,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "avg_pnl_per_closed_trade": (realized_pnl / Decimal(closed_count)) if closed_count else None,
        }

    @staticmethod
    def _signal_payload(row):
        """Expose stored signal evidence without inventing market facts."""
        metadata = row.metadata if isinstance(row.metadata, dict) else {}
        return {
            "id": row.id,
            "symbol": row.symbol,
            "direction": metadata.get("direction") or row.signal,
            "signal": row.signal,
            "confidence": row.confidence,
            "market_regime": metadata.get("market_regime") or metadata.get("regime") or "",
            "strategy": row.strategy.name,
            "strategy_slug": row.strategy.slug,
            "contract_type": metadata.get("contract_type") or metadata.get("contract") or "",
            "timeframe": row.configuration.timeframe if row.configuration else metadata.get("timeframe") or "",
            "display_name": metadata.get("display_name") or metadata.get("instrument_name") or "",
            "entry_price": row.entry_price,
            "stop_loss": row.stop_loss,
            "take_profit": row.take_profit,
            "entry_condition": metadata.get("entry_condition") or metadata.get("trigger_condition") or "",
            "trigger_status": metadata.get("trigger_status") or metadata.get("status") or "",
            "confirmation": metadata.get("confirmation") or metadata.get("confirmation_sequence") or "",
            "sequence": metadata.get("sequence") or metadata.get("digit_sequence") or metadata.get("price_sequence") or "",
            "technical_confluence": metadata.get("technical_confluence") or metadata.get("ta_confluence") or "",
            "price_action": metadata.get("price_action") or "",
            "support_resistance": metadata.get("support_resistance") or "",
            "volatility_check": metadata.get("volatility_check") or "",
            "trend_momentum": metadata.get("trend_momentum") or metadata.get("momentum_confirmation") or "",
            "risk_assessment": metadata.get("risk_assessment") or metadata.get("risk_gate") or "",
            "acceptance_reason": metadata.get("acceptance_reason") or metadata.get("reason") or "",
            "rejection_reason": metadata.get("rejection_reason") or "",
            "data_freshness": metadata.get("data_freshness") or metadata.get("freshness") or "",
            "broker_available": metadata.get("broker_available"),
            "backtest": metadata.get("backtest") or metadata.get("backtest_evidence") or "",
            "model": metadata.get("model") or metadata.get("model_version") or "",
            "was_executed": bool(metadata.get("was_executed", False)),
            "created_at": row.timestamp,
        }

    @action(detail=False, methods=["get"])
    def account_overview(self, request):
        account = get_active_account(request.user, request=request)
        if not account:
            return Response({
                "status": "unavailable",
                "data": {
                    "account": None,
                    "trading_stats": None,
                    "error": {"code": "NO_CONNECTED_ACCOUNT", "detail": "No connected broker account is available."},
                },
            }, status=status.HTTP_200_OK)

        positions = self._positions_for_account(request.user, account)
        stats = self._position_stats(positions)
        return Response({
            "status": "success",
            "data": {
                "account": {
                    "id": account.id,
                    "account_id": account.account_id,
                    "broker": account.broker.name,
                    "currency": account.currency,
                    "balance": account.balance,
                    "equity": account.equity if account.equity != 0 else None,
                    "margin": account.margin if account.margin != 0 else None,
                    "free_margin": account.free_margin if account.free_margin != 0 else None,
                    "net_profit_loss": stats["total_pnl"],
                    "realized_pnl": stats["realized_pnl"],
                    "unrealized_pnl": stats["unrealized_pnl"],
                    "last_synced_at": account.last_synced_at,
                    "data_freshness": (
                        "unknown" if account.last_synced_at is None
                        else "fresh" if (timezone.now() - account.last_synced_at).total_seconds() <= 60
                        else "stale"
                    ),
                    "is_connected": account.is_connected,
                },
                "trading_stats": stats,
            },
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def active_trades(self, request):
        account = get_active_account(request.user, request=request)
        rows = (
            self._orders_for_account(request.user, account)
            .filter(status="executed")
            .select_related("broker_account")
            [: self._limit(request)]
        )
        return Response({
            "status": "success",
            "count": len(rows),
            "data": [{
                "id": row.id,
                "symbol": row.symbol,
                "stake": row.stake,
                "direction": row.direction,
                "status": row.status,
                "strategy": row.strategy,
                "created_at": row.created_at,
                "broker_reference": row.broker_reference,
            } for row in rows],
        })

    @action(detail=False, methods=["get"])
    def trade_history(self, request):
        try:
            days = max(1, int(request.GET.get("days", 30)))
        except (TypeError, ValueError):
            days = 30
        start = timezone.now() - timedelta(days=days)
        account = get_active_account(request.user, request=request)
        rows = (
            self._orders_for_account(request.user, account)
            .filter(created_at__gte=start)
            [: self._limit(request)]
        )
        return Response({
            "status": "success",
            "total": len(rows),
            "count": len(rows),
            "data": [{
                "id": row.id,
                "symbol": row.symbol,
                "stake": row.stake,
                "direction": row.direction,
                "status": row.status,
                "strategy": row.strategy,
                "created_at": row.created_at,
                "broker_reference": row.broker_reference,
            } for row in rows],
        })

    @action(detail=False, methods=["get"])
    def performance_summary(self, request):
        account = get_active_account(request.user, request=request)
        if not account:
            return Response({
                "status": "unavailable",
                "data": None,
                "error": {"code": "NO_CONNECTED_ACCOUNT", "detail": "No connected broker account is available."},
            })

        stats = self._position_stats(self._positions_for_account(request.user, account))
        closed = self._positions_for_account(request.user, account).filter(status="closed")
        closed_values = list(closed.values_list("profit_loss", flat=True))
        total_profit = stats["realized_pnl"]
        best_trade = max(closed_values) if closed_values else None
        worst_trade = min(closed_values) if closed_values else None
        return Response({
            "status": "success",
            "data": {
                "total_trades": stats["total_trades"],
                "open_trades": stats["open_trades"],
                "closed_trades": stats["closed_trades"],
                "winning_trades": stats["wins"],
                "losing_trades": stats["losses"],
                "win_rate": stats["win_rate"],
                "total_profit": total_profit,
                "average_profit": stats["avg_pnl_per_closed_trade"],
                "sharpe_ratio": None,
                "best_trade": best_trade,
                "worst_trade": worst_trade,
            },
        })

    @action(detail=False, methods=["get"])
    def signals(self, request):
        symbol = str(request.GET.get("symbol") or "").strip()
        qs = StrategySignal.objects.select_related("strategy", "configuration").order_by("-timestamp")
        if symbol:
            qs = qs.filter(symbol=symbol)
        rows = qs[: self._limit(request)]
        return Response({"status": "success", "count": len(rows), "data": [self._signal_payload(row) for row in rows]})

    @action(detail=False, methods=["get"])
    def notifications(self, request):
        rows = Notification.objects.filter(user=request.user).order_by("-created_at")[: self._limit(request, 20)]
        return Response({"status": "success", "count": len(rows), "data": [{
            "id": row.id,
            "alert_type": row.category,
            "message": row.message,
            "channels": [row.channel],
            "delivered_channels": [row.channel] if row.status == "sent" else [],
            "status": row.status,
            "created_at": row.created_at,
        } for row in rows]})

    @action(detail=False, methods=["get"])
    def performance_metrics(self, request):
        account = get_active_account(request.user, request=request)
        if not account:
            return Response({
                "status": "unavailable",
                "data": None,
                "error": {"code": "NO_CONNECTED_ACCOUNT", "detail": "No connected broker account is available."},
            })

        stats = self._position_stats(self._positions_for_account(request.user, account))
        return Response({
            "status": "success",
            "data": {
                "total_trades": stats["total_trades"],
                "net_profit": stats["total_pnl"],
                "realized_pnl": stats["realized_pnl"],
                "unrealized_pnl": stats["unrealized_pnl"],
                "win_rate": stats["win_rate"],
                "max_drawdown": None,
                "sharpe_ratio": None,
            },
        })
