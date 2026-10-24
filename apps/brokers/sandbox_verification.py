"""Provider-specific sandbox verification contract.

This harness coordinates trusted, provider-authored checks. It never promotes a
broker or accepts a production account as a test target.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

REQUIRED_SANDBOX_CHECKS = (
    "authentication",
    "account_identity",
    "market_data",
    "order_submission",
    "cancellation",
    "fills",
    "ambiguous_execution_reconciliation",
)


class SandboxVerificationError(ValueError):
    """Raised when a sandbox verification cannot safely proceed."""


@dataclass(frozen=True)
class SandboxCheckResult:
    passed: bool
    evidence: str
    details: str = ""
    reconciled_before_resubmit: bool | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "passed" if self.passed else "failed",
            "evidence": self.evidence,
            "details": self.details,
            "resubmit_before_reconcile": self.reconciled_before_resubmit is False,
        }


class BrokerSandboxVerifier:
    """Run a complete set of trusted provider checks against an explicit sandbox."""

    def __init__(
        self,
        *,
        broker_slug: str,
        environment: str,
        account_identity_verified: bool,
        checks: dict[str, Callable[[], SandboxCheckResult]],
    ) -> None:
        if environment != "sandbox":
            raise SandboxVerificationError("Broker verification must target a provider sandbox/demo environment.")
        if not account_identity_verified:
            raise SandboxVerificationError("Sandbox account identity must be verified before any order test.")
        if not broker_slug or not broker_slug.replace("_", "").isalnum() or not broker_slug[0].isalpha():
            raise SandboxVerificationError("broker_slug is invalid.")
        missing = sorted(set(REQUIRED_SANDBOX_CHECKS) - set(checks))
        extra = sorted(set(checks) - set(REQUIRED_SANDBOX_CHECKS))
        if missing:
            raise SandboxVerificationError("Missing required provider checks: " + ", ".join(missing))
        if extra:
            raise SandboxVerificationError("Unknown provider checks: " + ", ".join(extra))
        self.broker_slug = broker_slug
        self.checks = checks

    def run(self, *, commit_sha: str) -> dict[str, Any]:
        """Execute trusted sandbox checks and return sanitized, evidence-backed results."""
        import re

        if not re.fullmatch(r"[0-9a-f]{40}", commit_sha or ""):
            raise SandboxVerificationError("A full candidate commit SHA is required.")
        results: dict[str, Any] = {}
        for name in REQUIRED_SANDBOX_CHECKS:
            try:
                result = self.checks[name]()
            except Exception:
                # Provider exceptions can contain tokens, request headers, or account data.
                results[name] = {
                    "status": "failed",
                    "evidence": "",
                    "details": "Provider check raised an exception; inspect sanitized CI logs.",
                }
                continue
            if not isinstance(result, SandboxCheckResult):
                results[name] = {
                    "status": "failed",
                    "evidence": "",
                    "details": "Provider check returned an invalid result type.",
                }
                continue
            if not result.evidence.strip():
                results[name] = {
                    "status": "failed",
                    "evidence": "",
                    "details": "Provider check supplied no evidence reference.",
                }
                continue
            if name == "ambiguous_execution_reconciliation" and result.reconciled_before_resubmit is not True:
                results[name] = {
                    "status": "failed",
                    "evidence": result.evidence,
                    "details": "Ambiguous order outcomes must be reconciled before another submission.",
                    "resubmit_before_reconcile": result.reconciled_before_resubmit is False,
                }
                continue
            results[name] = result.as_dict()
        passed = all(results.get(name, {}).get("status") == "passed" for name in REQUIRED_SANDBOX_CHECKS)
        return {
            "broker_slug": self.broker_slug,
            "environment": "sandbox",
            "commit_sha": commit_sha,
            "checks": results,
            "passed": passed,
            "production_enabled": False,
            "human_approval_required": True,
        }
