from dataclasses import dataclass, field


NOT_CONFIGURED = "No infrastructure provider is configured for this operation; no changes were made."


@dataclass
class OperationResult:
    status: str
    details: dict = field(default_factory=dict)


class DeploymentService:
    strategies = ["rolling", "blue-green", "canary", "ab", "rollback"]

    def deploy(self, environment, version, strategy="rolling"):
        return OperationResult("not_configured", {
            "environment": environment,
            "version": version,
            "strategy": strategy,
            "detail": NOT_CONFIGURED,
        })

    def rollback(self, environment):
        return OperationResult("not_configured", {
            "environment": environment,
            "detail": NOT_CONFIGURED,
        })


class BackupService:
    def schedule(self, target="postgres", backup_type="incremental"):
        return OperationResult("not_configured", {
            "target": target,
            "backup_type": backup_type,
            "detail": NOT_CONFIGURED,
        })


class RestoreService:
    def validate(self, backup_id):
        return OperationResult("not_configured", {
            "backup_id": backup_id,
            "detail": "Restore validation is unavailable until a backup provider is configured.",
        })


class ScalingService:
    def plan(self, metric, value):
        return OperationResult("not_configured", {
            "metric": metric,
            "value": value,
            "detail": "Scaling is not connected to a live infrastructure provider.",
        })


class SecretService:
    def rotate(self, name):
        return OperationResult("not_configured", {
            "name": name,
            "detail": "Secret rotation is not connected to a secret manager; no secret was rotated.",
        })


class ClusterService:
    def health(self):
        return {
            "cluster_health": "unknown",
            "running_pods": None,
            "auto_scaling": "unknown",
            "source": "cluster_provider_not_configured",
        }


class InfrastructureService:
    def provision_plan(self):
        return {
            "terraform": False,
            "ansible": False,
            "helm": False,
            "docker_compose": False,
            "status": "not_configured",
        }


class PipelineService:
    stages = [
        "lint", "formatting", "static_analysis", "unit_tests", "integration_tests",
        "security_scans", "container_build", "docker_push", "migration", "deployment",
        "smoke_tests", "rollback",
    ]

    def status(self):
        return {"stages": self.stages, "status": "not_configured"}
