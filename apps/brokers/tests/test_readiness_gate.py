import unittest

from scripts.validate_broker_readiness import REQUIRED_CHECKS, validate


def passed_manifest():
    return {
        "broker_slug": "example",
        "environment": "sandbox",
        "commit_sha": "a" * 40,
        "static_validation": "passed",
        "isolated_tests": "passed",
        "checks": {
            name: {"status": "passed", "evidence": f"sanitized-report#{name}"}
            for name in REQUIRED_CHECKS
        },
        "human_approval": {"reviewer": "maintainer", "approved_at": "2026-10-24T12:00:00Z"},
    }


class BrokerReadinessGateTests(unittest.TestCase):
    def test_accepts_complete_sandbox_evidence_for_expected_commit(self):
        self.assertEqual(validate(passed_manifest(), "a" * 40), [])

    def test_rejects_failed_or_missing_provider_check(self):
        manifest = passed_manifest()
        manifest["checks"]["fills"]["status"] = "failed"
        manifest["checks"].pop("market_data")
        errors = validate(manifest)
        self.assertTrue(any("fills" in error for error in errors))
        self.assertTrue(any("market_data" in error for error in errors))

    def test_rejects_commit_mismatch_and_missing_human_approval(self):
        manifest = passed_manifest()
        manifest["human_approval"] = {}
        errors = validate(manifest, "b" * 40)
        self.assertTrue(any("does not match" in error for error in errors))
        self.assertTrue(any("human approval" in error for error in errors))

    def test_rejects_unsafe_ambiguous_order_retry(self):
        manifest = passed_manifest()
        manifest["checks"]["ambiguous_execution_reconciliation"]["resubmit_before_reconcile"] = True
        self.assertTrue(any("reconciled before resubmission" in error for error in validate(manifest)))


if __name__ == "__main__":
    unittest.main()
