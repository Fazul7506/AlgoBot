import unittest

from apps.brokers.sandbox_verification import (
    BrokerSandboxVerifier,
    REQUIRED_SANDBOX_CHECKS,
    SandboxCheckResult,
    SandboxVerificationError,
)


class BrokerSandboxVerifierTests(unittest.TestCase):
    def make_checks(self, reconciliation=True):
        return {
            name: (lambda name=name: SandboxCheckResult(
                passed=True,
                evidence=f"sanitized-evidence:{name}",
                reconciled_before_resubmit=reconciliation if name == "ambiguous_execution_reconciliation" else None,
            ))
            for name in REQUIRED_SANDBOX_CHECKS
        }

    def test_requires_sandbox_and_verified_account_identity(self):
        with self.assertRaises(SandboxVerificationError):
            BrokerSandboxVerifier(
                broker_slug="example", environment="production",
                account_identity_verified=True, checks=self.make_checks(),
            )
        with self.assertRaises(SandboxVerificationError):
            BrokerSandboxVerifier(
                broker_slug="example", environment="sandbox",
                account_identity_verified=False, checks=self.make_checks(),
            )

    def test_requires_every_provider_specific_check(self):
        checks = self.make_checks()
        checks.pop("fills")
        with self.assertRaisesRegex(SandboxVerificationError, "fills"):
            BrokerSandboxVerifier(
                broker_slug="example", environment="sandbox",
                account_identity_verified=True, checks=checks,
            )

    def test_passes_only_when_all_sandbox_checks_have_evidence(self):
        verifier = BrokerSandboxVerifier(
            broker_slug="example", environment="sandbox",
            account_identity_verified=True, checks=self.make_checks(),
        )
        report = verifier.run(commit_sha="a" * 40)
        self.assertTrue(report["passed"])
        self.assertFalse(report["production_enabled"])
        self.assertTrue(report["human_approval_required"])

    def test_fails_ambiguous_order_check_without_reconciliation(self):
        verifier = BrokerSandboxVerifier(
            broker_slug="example", environment="sandbox",
            account_identity_verified=True, checks=self.make_checks(reconciliation=False),
        )
        report = verifier.run(commit_sha="a" * 40)
        self.assertFalse(report["passed"])
        self.assertEqual(
            report["checks"]["ambiguous_execution_reconciliation"]["status"], "failed"
        )

    def test_sanitizes_provider_exceptions_and_requires_full_commit(self):
        checks = self.make_checks()
        checks["market_data"] = lambda: (_ for _ in ()).throw(RuntimeError("secret token should not leak"))
        verifier = BrokerSandboxVerifier(
            broker_slug="example", environment="sandbox",
            account_identity_verified=True, checks=checks,
        )
        report = verifier.run(commit_sha="a" * 40)
        self.assertFalse(report["passed"])
        self.assertNotIn("secret token", str(report))
        with self.assertRaises(SandboxVerificationError):
            verifier.run(commit_sha="short")


if __name__ == "__main__":
    unittest.main()
