from apps.enterprise.services import DecisionEngine, EnterpriseOrchestrator, MultiAgentCoordinator


def test_enterprise_intelligence_services_do_not_fabricate_state():
    control_center = EnterpriseOrchestrator().control_center()
    assert control_center["health_score"] is None
    assert control_center["system_status"] in {"healthy", "down", "unknown"}
    assert all(agent["status"] == "not_configured" for agent in MultiAgentCoordinator().status())
    decision = DecisionEngine().decide()
    assert decision.status == "requires_context"
