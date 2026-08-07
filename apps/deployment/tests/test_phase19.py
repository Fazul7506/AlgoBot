from apps.deployment.services import DeploymentService, PipelineService, ClusterService

def test_deployment_platform_services():
    assert DeploymentService().deploy("staging", "1.0").status == "started"
    assert "security_scans" in PipelineService().stages
    assert ClusterService().health()["cluster_health"] == "healthy"
