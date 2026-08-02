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

class KillSwitchService:
    def activate(self,user,reason='Manual kill switch',activated_by=None): logger.critical('Kill switch activated for %s: %s',user,reason); return RiskRepository().activate_kill_switch(user,reason,activated_by)
    def deactivate(self,user): return RiskRepository().deactivate_kill_switch(user)
    def pause_all_trading(self,user,reason='Trading paused'): return self.activate(user,reason)
    def resume_trading(self,user): return self.deactivate(user)
    def emergency_shutdown(self,user,reason='Emergency shutdown'): return self.activate(user,reason)
    def is_active(self,user): return RiskRepository().active_kill_switch(user) is not None

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
    def dashboard(self,user): return {'risk_score':0,'today_profit_loss':0,'current_drawdown':0,'maximum_drawdown':0,'portfolio_exposure':ExposureService().summary(user)['overall'],'margin_level':0,'free_margin':0,'open_risk':0,'daily_loss_remaining':0,'kill_switch_status':KillSwitchService().is_active(user),'circuit_breaker_status':False}

# public aliases
RiskRepository=RiskRepository; PositionSizingService=PositionSizingService; DrawdownService=DrawdownService; ExposureService=ExposureService; CorrelationService=CorrelationService; PortfolioRiskService=PortfolioRiskService
