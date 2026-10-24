# Broker adapter validation, sandbox evidence, and approval

## Non-negotiable promotion order

1. Generate a draft only. AI output is untrusted source and is never enabled automatically.
2. Run `python scripts/validate_broker_draft.py <draft-directory>`. A failed static check is a hard stop.
3. Run adapter contract tests in the disposable isolated workflow. Do not expose deployment secrets, provider credentials, write tokens, host sockets, or production account access to the test container.
4. Validate provider-specific behavior only against the provider's official demo/sandbox: authentication, account identity, market data, order submission, cancellation, fills, and ambiguous execution outcomes.
5. Record results in a reviewed JSON evidence manifest and run `python scripts/validate_broker_readiness.py <manifest> --commit <full-sha>`.
6. Require human review and protected-environment approval before any separate change may register the provider as production-supported. The gate validates evidence only; it never registers or enables a broker.

## Isolated execution expectations

The dedicated GitHub Actions workflow builds the test image before execution, then runs it with network access disabled, a read-only root filesystem, all Linux capabilities dropped, no-new-privileges, process/memory/CPU limits, and only the candidate source mounted read-only. No production credentials are passed. This is defense in depth, not a substitute for patching the runner/container runtime or reviewing malicious source. Never run generated code on a developer workstation or production service as a validation shortcut.

The candidate directory may contain only `adapter.py`, `test_adapter_contract.py`, and `README.md`. The test step is skipped unless the manually selected candidate directory exists; the static gate and focused Django tests still run on pull requests.

## Evidence manifest

The manifest must identify the broker slug, sandbox environment, exact full commit SHA, static and isolated-test results, a human reviewer and approval timestamp, plus a non-empty evidence reference for each required sandbox check. Evidence should link to sanitized test reports or provider sandbox logs, never contain tokens, secrets, account numbers, or personal data. The readiness gate rejects missing or failed checks and does not modify broker registry state.

Required `checks` keys: `authentication`, `account_identity`, `market_data`, `order_submission`, `cancellation`, `fills`, and `ambiguous_execution_reconciliation`. Every check must have `status: "passed"` and an `evidence` reference. Ambiguous execution tests must demonstrate reconciliation before any further submission; automatic blind retry is prohibited.

## Reviewed pull-request creation

A reviewed draft can be promoted to a feature branch and proposed pull request only after static and isolated tests pass and a maintainer has inspected the diff. PR creation must not merge, deploy, or activate a broker. Keep the integration-agent PR in draft until the checks are green and the workflow is reviewed. Configure the repository's `broker-production-approval` environment with required reviewers before using any production approval workflow.


## Deriv demo smoke verification

Run the manual **Deriv Demo Sandbox Smoke Verification** workflow only after configuring
the `DERIV_DEMO_TOKEN` secret and `DERIV_APP_ID` Actions variable in the
`broker-production-approval` environment. The workflow uses the PAT to authorize
against Deriv's WebSocket API and fails closed unless Deriv explicitly reports both
a `VRTC` login ID and `is_virtual` true. It then checks a live quote and available
contracts for the selected symbol. It never prints the token, account ID, balance,
or raw provider responses.

This smoke workflow intentionally does **not** claim the full sandbox gate is passed:
it does not submit an order and cannot verify fills, cancellation/close behavior, or
ambiguous-execution reconciliation. Those checks require a separately reviewed,
explicitly opt-in demo trade lifecycle test. Do not use this smoke result as the
seven-check evidence manifest required for broker readiness or production approval.
