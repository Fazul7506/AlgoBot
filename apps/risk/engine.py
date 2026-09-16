import logging
import time

from .repositories import RiskRepository
from .services import RiskService
from .validator import RiskValidator

logger = logging.getLogger(__name__)


# Routing/transport metadata is deliberately separate from numeric risk inputs.
# Client requests can carry broker_source, contract_type, signal_id, etc.; those
# fields must never be expanded into the RiskService.score(**kwargs) call.
RISK_SCORE_FIELDS = frozenset({
    'volatility',
    'exposure',
    'drawdown',
    'correlation',
    'margin',
    'market_conditions',
    'strategy_confidence',
})


class RiskEngine:
    @staticmethod
    def _score_context(context):
        context = context or {}
        return {key: context[key] for key in RISK_SCORE_FIELDS if key in context}

    def evaluate_order(self, order, context=None):
        start = time.perf_counter()
        context = context or {}
        repo = RiskRepository()
        score = RiskService().score(**self._score_context(context))
        try:
            RiskValidator().validate_order(order)
            routing = getattr(order, 'routing_context', {}) or {}
            ai = routing.get('ai_consensus') or routing.get('ai_decision') or {}
            if ai:
                decision = str(ai.get('decision') or ai.get('recommendation') or '').upper()
                confidence = float(ai.get('confidence', 0) or 0)
                models_used = int(ai.get('models_used', 0) or 0)
                if decision not in {'BUY', 'SELL'}:
                    raise PermissionError('Ensemble consensus is not actionable')
                intended = str(order.direction).upper()
                if decision != intended:
                    raise PermissionError('Order direction conflicts with ensemble consensus')
                if confidence < 65.0:
                    raise PermissionError(f'Ensemble confidence {confidence:.2f}% below 65.00% gate')
                # ai_decision is used by the lightweight execution gate and may
                # not carry a model count; only enforce the count when supplied.
                if 'models_used' in ai and models_used < 1:
                    raise PermissionError('No trained ensemble models available')
            approved = score < 80
            reason = '' if approved else 'Extreme risk score'
        except Exception as exc:
            approved = False
            reason = str(exc)
        assessment = repo.assess(
            order,
            score,
            approved,
            reason,
            {
                'stake': str(order.stake),
                'ai_consensus': (getattr(order, 'routing_context', {}) or {}).get('ai_consensus', {}),
            },
        )
        logger.info(
            'Risk assessment order=%s approved=%s score=%s latency_ms=%.3f',
            order.pk,
            approved,
            score,
            (time.perf_counter() - start) * 1000,
        )
        return assessment

    def approve_or_raise(self, order, context=None):
        assessment = self.evaluate_order(order, context)
        if not assessment.approved:
            raise PermissionError(assessment.rejection_reason)
        return assessment
