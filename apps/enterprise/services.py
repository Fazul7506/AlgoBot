"""Enterprise-facing services.

Enterprise surfaces must describe actual platform state. They must not return
invented health, confidence, approval, or agent metrics merely to populate a
dashboard.
"""
from dataclasses import dataclass, field


@dataclass
class IntelligenceResult:
    status: str
    data: dict = field(default_factory=dict)


class MarketRegimeService:
    def analyze(self, metrics=None):
        return {"regime": "unknown", "volatility": "unknown", "confidence": None, "metrics": metrics or {}}


class DecisionEngine:
    def decide(self, context=None):
        if not context:
            return IntelligenceResult("requires_context", {"reason": "Decision context is required"})
        return IntelligenceResult("not_configured", {"reason": "No enterprise decision policy is registered"})


class MultiAgentCoordinator:
    agents = [
        "Market Analyst Agent", "Strategy Analyst Agent", "Risk Analyst Agent",
        "Portfolio Manager Agent", "Execution Agent", "Broker Agent",
        "AI Model Manager", "News Intelligence Agent", "SMC Specialist",
        "ICT Specialist", "Options Specialist", "Volatility Specialist",
        "Monitoring Agent", "Recovery Agent", "Optimization Agent",
    ]

    def status(self):
        return [{"name": agent, "status": "not_configured"} for agent in self.agents]


class EnterpriseOrchestrator:
    def control_center(self):
        from apps.monitoring.services import MonitoringEngine
        dashboard = MonitoringEngine().dashboard()
        return {
            "system_status": dashboard.get("overall_system_health", "unknown"),
            "health_score": None,
            "agents": MultiAgentCoordinator().status(),
        }


class KnowledgeBaseService:
    def search(self, query=""):
        return {"query": query, "results": []}


class StrategyEvolutionService:
    def evolve(self):
        return IntelligenceResult("not_configured", {"reason": "No enterprise strategy-evolution workflow is registered"})


class PortfolioOptimizationService:
    def optimize(self):
        return IntelligenceResult("not_configured", {"reason": "Use the canonical portfolio optimization service"})


class RiskGovernor:
    def evaluate(self, decision=None):
        return IntelligenceResult("requires_risk_context", {"reason": "A broker/account risk context is required"})


class ExplainableAIService:
    def explain(self, decision):
        return {"decision": decision, "features": [], "confidence": None, "status": "not_configured"}


class SelfHealingService:
    def execute(self):
        return IntelligenceResult("not_configured", {"reason": "Use the canonical monitoring/self-healing controls"})


class GovernanceService:
    def policies(self):
        return []


class OptimizationService:
    def run(self, objective="sharpe_ratio"):
        return IntelligenceResult("not_configured", {"objective": objective, "reason": "No enterprise optimization job has been registered"})
