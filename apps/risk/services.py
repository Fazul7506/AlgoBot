import logging
from decimal import Decimal
from django.utils import timezone
from .repositories import RiskRepository
from .sizing import PositionSizingService
from .drawdown import DrawdownService
from .exposure import ExposureService
from .correlation import CorrelationService
from .portfolio import PortfolioRiskService
logger=logging.getLogger(__name__)

class RiskService:
    def profile(self,user): return RiskRepository().profile_for_user(user)
    def score(self,*,volatility=0,exposure=0,drawdown=0,correlation=0,margin=0,market_conditions=0,strategy_confidence=1):
        raw=Decimal(str(volatility))*20+Decimal(str(exposure))*20+Decimal(str(drawdown))*25+Decimal(str(correlation))*15+Decimal(str(margin))*10+Decimal(str(market_conditions))*10+(1-Decimal(str(strategy_confidence)))*20
        return int(max(0,min(100,raw)))
    def label(self,score): return 'Low Risk' if score<30 else 'Medium Risk' if score<60 else 'High Risk' if score<80 else 'Extreme Risk'

class MarginService:
    def snapshot(self,balance,used_margin):
        b=Decimal(str(balance or 0)); used=Decimal(str(used_margin or 0)); free=b-used; level=(b/used*100) if used else Decimal('9999')
        return {'available_balance':b,'used_margin':used,'free_margin':free,'margin_level':level,'margin_call':level<100,'stop_out_risk':level<50}

class CircuitBreakerService:
    def evaluate(self,broker_unstable=False,websocket_disconnected=False,market_volatility=0,latency_ms=0,strategy_malfunction=False,risk_limits_exceeded=False):
        reasons=[]
        if broker_unstable: reasons.append('Broker unstable')
        if websocket_disconnected: reasons.append('WebSocket disconnected')
        if Decimal(str(market_volatility))>Decimal('0.08'): reasons.append('Market volatility too high')
        if latency_ms>1000: reasons.append('Latency exceeds threshold')
        if strategy_malfunction: reasons.append('Strategy malfunction detected')
        if risk_limits_exceeded: reasons.append('Risk limits exceeded')
        return {'active':bool(reasons),'reasons':reasons}

class TradingSessionRiskService:
    def validate(self,now=None,allowed_hours=None,forbidden_hours=None,weekend_allowed=False,holidays=None,maintenance_windows=None):
        now=now or timezone.now(); h=now.hour
        if not weekend_allowed and now.weekday()>=5: return False,'Weekend trading forbidden'
        if holidays and now.date().isoformat() in holidays: return False,'Holiday trading forbidden'
        if allowed_hours and h not in allowed_hours: return False,'Outside allowed trading hours'
        if forbidden_hours and h in forbidden_hours: return False,'Forbidden trading hour'
        return True,''

class RiskMonitoringService:
    """Expose risk telemetry derived from persisted account and risk state."""
    def dashboard(self, user):
        from apps.brokers.models import BrokerAccount
        from .models import DrawdownHistory

        profile = RiskRepository().profile_for_user(user)
        exposure = ExposureService().summary(user)
        accounts = list(BrokerAccount.objects.filter(user=user, status="active").only("balance", "equity", "margin", "free_margin"))

        latest = DrawdownService().state(user, profile)
        current_drawdown = Decimal(str(latest.get("drawdown_percent") or 0))
        maximum_drawdown = DrawdownHistory.objects.filter(user=user).order_by("-drawdown_percent").values_list("drawdown_percent", flat=True).first() or Decimal("0")

        total_balance = sum((Decimal(str(account.balance or 0)) for account in accounts), Decimal("0"))
        total_free_margin = sum((Decimal(str(account.free_margin or 0)) for account in accounts), Decimal("0"))
        total_margin = sum((Decimal(str(account.margin or 0)) for account in accounts), Decimal("0"))
        margin_level = (total_balance / total_margin * Decimal("100")) if total_margin > 0 else None

        exposure_value = Decimal(str(exposure.get("overall") or 0))
        exposure_ratio = (exposure_value / total_balance) if total_balance > 0 else Decimal("0")
        margin_risk = Decimal("1") if margin_level is None else max(Decimal("0"), Decimal("1") - margin_level / Decimal("100"))
        risk_score = self._risk_score(drawdown=current_drawdown, exposure=exposure_ratio, margin=margin_risk)

        return {
            "risk_score": risk_score,
            "today_profit_loss": None,
            "current_drawdown": current_drawdown,
            "maximum_drawdown": maximum_drawdown,
            "portfolio_exposure": exposure_value,
            "margin_level": margin_level,
            "free_margin": total_free_margin,
            "open_risk": exposure_value,
            "daily_loss_remaining": None,
            "circuit_breaker_status": None,
            "drawdown_state": latest,
            "account_count": len(accounts),
        }

    @staticmethod
    def _risk_score(*, drawdown, exposure, margin):
        return RiskService().score(
            drawdown=min(max(float(drawdown), 0.0), 1.0),
            exposure=min(max(float(exposure), 0.0), 1.0),
            margin=min(max(float(margin), 0.0), 1.0),
        )


# public aliases
RiskRepository=RiskRepository; PositionSizingService=PositionSizingService; DrawdownService=DrawdownService; ExposureService=ExposureService; CorrelationService=CorrelationService; PortfolioRiskService=PortfolioRiskService
