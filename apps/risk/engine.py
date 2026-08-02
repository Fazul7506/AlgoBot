import time, logging
from .repositories import RiskRepository
from .services import RiskService
from .validator import RiskValidator
logger=logging.getLogger(__name__)
class RiskEngine:
    def evaluate_order(self,order,context=None):
        start=time.perf_counter(); context=context or {}; repo=RiskRepository(); score=RiskService().score(**context)
        try:
            RiskValidator().validate_order(order); approved=score<80; reason='' if approved else 'Extreme risk score'
        except Exception as exc:
            approved=False; reason=str(exc)
        assessment=repo.assess(order,score,approved,reason,{'stake':str(order.stake)})
        logger.info('Risk assessment order=%s approved=%s score=%s latency_ms=%.3f',order.pk,approved,score,(time.perf_counter()-start)*1000)
        return assessment
    def approve_or_raise(self,order,context=None):
        a=self.evaluate_order(order,context)
        if not a.approved: raise PermissionError(a.rejection_reason)
        return a
