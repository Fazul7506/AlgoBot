from apps.deployment.services import DeploymentService, PipelineService, ClusterService


def test_deployment_platform_services_do_not_claim_unconfigured_operations_succeeded():
    assert DeploymentService().deploy("staging", "1.0").status == "not_configured"
    assert DeploymentService().rollback("production").status == "not_configured"
    assert "security_scans" in PipelineService().stages
    assert PipelineService().status()["status"] == "not_configured"
    health = ClusterService().health()
    assert health["cluster_health"] == "unknown"
    assert health["running_pods"] is None
