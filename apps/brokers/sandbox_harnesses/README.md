# Trusted broker sandbox harnesses

A provider harness is trusted application code, not AI-generated adapter code. It must be reviewed and merged to main before the sandbox workflow can execute it. Create <broker_slug>.py here only after confirming the provider's official demo API documentation and supported order lifecycle.

The module must expose:
- verify_sandbox_account_identity() -> bool: authenticate using sandbox-only credentials, positively verify the account is demo/virtual, and return True only when provider-returned identity fields prove this. Fail closed otherwise.
- build_sandbox_checks() -> dict[str, Callable[[], SandboxCheckResult]]: return exactly the seven checks listed in apps/brokers/sandbox_verification.py::REQUIRED_SANDBOX_CHECKS.

Every check must exercise a real provider sandbox behavior and return SandboxCheckResult(passed=..., evidence='sanitized stable evidence reference'). The reconciliation check must set reconciled_before_resubmit=True only after demonstrating that an ambiguous order result was queried/reconciled before any possible resubmission. Never blindly resubmit an order after a timeout.

## Required provider-specific behavior
1. Authentication using a sandbox/demo credential.
2. Account identity verified as sandbox/demo before any order-related operation.
3. Market-data retrieval.
4. A small, bounded sandbox order submission with a unique client/order reference.
5. Provider-supported cancellation, or explicitly documented close/sell semantics where cancellation is not supported. Do not mislabel closing a position as cancelling an order.
6. Fill/execution confirmation from provider state, not merely an accepted response.
7. An ambiguous-execution reconciliation test that queries provider state and proves the safe no-duplicate policy.

Use only provider-documented endpoints and test instruments. Enforce order-size limits, avoid production accounts, redact credentials and account identifiers, use bounded timeouts, and clean up remaining sandbox orders/positions in a finally path where supported. Never return raw provider responses in evidence or include credentials in source, logs, fixtures, or artifacts.

## Run procedure
1. Review and merge the adapter draft and trusted harness as separate reviewed code changes. Never run generated adapter code with sandbox secrets.
2. Configure the GitHub Actions environment named broker-sandbox-<broker_slug> with sandbox-only secrets as required by the provider: BROKER_SANDBOX_API_TOKEN, BROKER_SANDBOX_APP_ID, BROKER_SANDBOX_CLIENT_ID, BROKER_SANDBOX_CLIENT_SECRET.
3. Run Provider-Specific Broker Sandbox Lifecycle Verification manually on main, providing the broker slug and full adapter commit SHA.
4. Inspect the sanitized evidence artifact and resolve any failed check. A passing workflow is evidence for the exact adapter SHA only.
5. Complete the separate readiness manifest, record the actual human reviewer and timestamp, and run Broker Production Readiness Approval. This records the protected approval boundary only; registration/activation still requires a separate reviewed code change.

If a provider cannot support a required check, do not mark it passed or pretend another operation is equivalent. Document the limitation and keep the candidate blocked until an explicitly approved policy supports that provider.