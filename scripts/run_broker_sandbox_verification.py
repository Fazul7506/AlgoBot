#!/usr/bin/env python3
"""Run a reviewed, provider-specific sandbox harness and emit sanitized evidence.

The harness must be trusted repository code under apps/brokers/sandbox_harnesses/.
Generated adapter source is never imported by this runner. Provider credentials must
be sandbox-only GitHub Actions secrets and must never be returned in evidence.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

from apps.brokers.sandbox_verification import (
    BrokerSandboxVerifier,
    SandboxVerificationError,
)

ROOT = Path(__file__).resolve().parents[1]
HARNESS_ROOT = (ROOT / "apps" / "brokers" / "sandbox_harnesses").resolve()
SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def load_trusted_harness(slug: str) -> ModuleType:
    if not SLUG_RE.fullmatch(slug):
        raise ValueError("Invalid broker slug.")
    candidate = HARNESS_ROOT / f"{slug}.py"
    if candidate.is_symlink():
        raise ValueError("Trusted harness path must not be a symlink.")
    path = candidate.resolve()
    if path.parent != HARNESS_ROOT or not path.is_file():
        raise ValueError(
            f"No trusted provider harness found at apps/brokers/sandbox_harnesses/{slug}.py. "
            "Implement and review provider-specific sandbox checks before running this gate."
        )
    spec = importlib.util.spec_from_file_location(f"trusted_broker_sandbox_{slug}", path)
    if spec is None or spec.loader is None:
        raise ValueError("Could not load the trusted provider harness.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    required = ("verify_sandbox_account_identity", "build_sandbox_checks")
    if any(not callable(getattr(module, name, None)) for name in required):
        raise ValueError("Trusted harness must implement verify_sandbox_account_identity() and build_sandbox_checks().")
    return module


def run(slug: str, commit_sha: str, output: Path) -> dict[str, Any]:
    if not SHA_RE.fullmatch(commit_sha):
        raise ValueError("A full 40-character candidate commit SHA is required.")
    if os.environ.get("BROKER_TARGET_ENVIRONMENT") != "sandbox":
        raise ValueError("Set BROKER_TARGET_ENVIRONMENT=sandbox; production targets are forbidden.")
    harness = load_trusted_harness(slug)

    # Verify the provider's account identity before any order-related checks execute.
    try:
        identity_verified = harness.verify_sandbox_account_identity()
    except Exception:
        raise ValueError("Sandbox account identity verification failed; provider details suppressed.") from None
    if identity_verified is not True:
        raise ValueError("Provider did not positively verify a demo/sandbox account identity.")

    try:
        checks = harness.build_sandbox_checks()
    except Exception:
        raise ValueError("Could not construct trusted provider checks; details suppressed.") from None
    if not isinstance(checks, dict):
        raise ValueError("Trusted harness must return a mapping of required check names to callables.")

    verifier = BrokerSandboxVerifier(
        broker_slug=slug,
        environment="sandbox",
        account_identity_verified=True,
        checks=checks,
    )
    report = verifier.run(commit_sha=commit_sha)
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report["static_validation"] = "not_recorded"
    report["isolated_tests"] = "not_recorded"
    report["human_approval"] = None
    report["production_enabled"] = False
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker-slug", required=True)
    parser.add_argument("--commit", required=True, help="Full candidate adapter commit SHA")
    parser.add_argument("--output", type=Path, default=Path("sandbox-readiness.json"))
    args = parser.parse_args()
    try:
        report = run(args.broker_slug, args.commit, args.output)
    except (OSError, ValueError, SandboxVerificationError) as exc:
        print(f"Sandbox verification blocked: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "passed": report["passed"],
        "broker_slug": report["broker_slug"],
        "environment": report["environment"],
        "commit_sha": report["commit_sha"],
        "evidence_file": str(args.output),
        "human_approval_required": True,
        "production_enabled": False,
    }, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
