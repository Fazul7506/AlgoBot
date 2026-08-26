import time, logging
from .repositories import RiskRepository
from .services import RiskService
from .validator import RiskValidator
logger=logging.getLogger(__name__)

class RiskEngine:
    def evaluate_order(self,order,context=None):
        start=time.perf_counter(); context=context or {}; repo=RiskRepository(); score=RiskService().score(**context)
        try:
            RiskValidator().validate_order(order)
            ai=(getattr(order,'validation_context',{}) or {}).get('ai_consensus') or {}
            if ai:
                decision=str(ai.get('decision','')).upper()
                confidence=float(ai.get('confidence',0) or 0)
                if decision not in {'BUY','SELL'}:
                    raise PermissionError('Ensemble consensus is not actionable')
                if decision != str(order.direction).upper():
                    raise PermissionError('Order direction conflicts with ensemble consensus')
                if confidence < 65.0:
                    raise PermissionError(f'Ensemble confidence {confidence:.2f}% below 65.00% gate')
                if int(ai.get('models_used',0) or 0) < 1:
                    raise PermissionError('No trained ensemble models available')
            approved=score<80; reason='' if approved else 'Extreme risk score'
        except Exception as exc:
            approved=False; reason=str(exc)
        assessment=repo.assess(order,score,approved,reason,{'stake':str(order.stake),'ai_consensus':(getattr(order,'validation_context',{}) or {}).get('ai_consensus',{})})
        logger.info('Risk assessment order=%s approved=%s score=%s latency_ms=%.3f',order.pk,approved,score,(time.perf_counter()-start)*1000)
        return assessment
    def approve_or_raise(self,order,context=None):
        a=self.evaluate_order(order,context)
        if not a.approved: raise PermissionError(a.rejection_reason)
        return a
