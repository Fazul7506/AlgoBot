#!/usr/bin/env python3
"""Validate evidence manifest; never enables or registers a broker."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED_CHECKS = (
    "authentication",
    "account_identity",
    "market_data",
    "order_submission",
    "cancellation",
    "fills",
    "ambiguous_execution_reconciliation",
)


def validate(manifest: object, expected_commit: str | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["Manifest must be a JSON object."]
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,47}", str(manifest.get("broker_slug", ""))):
        errors.append("broker_slug must be a safe lowercase slug.")
    if manifest.get("environment") != "sandbox":
        errors.append("Provider evidence must come from the provider's sandbox/demo environment.")
    commit = manifest.get("commit_sha", "")
    if not re.fullmatch(r"[0-9a-f]{40}", str(commit)):
        errors.append("commit_sha must be a full 40-character Git commit SHA.")
    if expected_commit and commit != expected_commit:
        errors.append("Evidence commit_sha does not match the candidate commit.")
    checks = manifest.get("checks")
    if not isinstance(checks, dict):
        errors.append("checks must be an object of provider-specific verification results.")
        checks = {}
    for name in REQUIRED_CHECKS:
        result = checks.get(name)
        if not isinstance(result, dict) or result.get("status") != "passed":
            errors.append(f"Required sandbox check is not passed: {name}.")
            continue
        evidence = result.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            errors.append(f"Sandbox evidence reference is missing for {name}.")
    reconciliation = checks.get("ambiguous_execution_reconciliation", {})
    if isinstance(reconciliation, dict) and reconciliation.get("resubmit_before_reconcile") is True:
        errors.append("Unsafe order retry policy: ambiguous outcomes must be reconciled before resubmission.")
    if manifest.get("static_validation") != "passed":
        errors.append("Static validation must be recorded as passed.")
    if manifest.get("isolated_tests") != "passed":
        errors.append("Isolated adapter contract tests must be recorded as passed.")
    approval = manifest.get("human_approval")
    if not isinstance(approval, dict) or not approval.get("reviewer") or not approval.get("approved_at"):
        errors.append("Recorded human approval (reviewer and approved_at) is required.")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--commit", help="Expected candidate commit SHA")
    args = parser.parse_args()
    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        print("Readiness gate failed: manifest is missing or invalid JSON.", file=sys.stderr)
        return 2
    errors = validate(data, args.commit)
    print(json.dumps({"passed": not errors, "errors": errors}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
