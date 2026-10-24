# AI-assisted broker integration workflow

## What this adds

AlgoBot already has a common asynchronous contract in `apps/brokers/adapters/base.py`, a lazy adapter registry in `apps/brokers/services.py`, and a catalog that includes providers which are only scaffolds. The `BrokerIntegrationAgent` uses the OpenAI Responses API to produce a reviewable adapter/test/documentation draft from official provider API documentation. It does not pretend that a catalog entry is a working integration.

## Use

1. Configure `OPENAI_API_KEY` as a deployment secret (never commit it) and optionally set `OPENAI_BROKER_AGENT_MODEL` to an enabled model.
2. Supply the provider name, a safe slug, and official API documentation or an accurate factual summary to `BrokerIntegrationAgent.generate(...)`.
3. Review `implementation_plan`, `assumptions`, `provider_questions`, and each returned file. Generated source is untrusted input.
4. Copy reviewed draft files into a feature branch; complete adapter-specific tests and run the full project test suite and security checks.
5. Verify OAuth/API credentials, scopes, redirects, rate limits, market-data normalization, order status mapping, account ownership, and sandbox behavior against the provider.
6. Only after human review and verified sandbox evidence should a separate change register the adapter and mark the provider production-supported.

Example from Django shell (pass only public documentation, never credentials):

```python
from apps.brokers.integration_agent import BrokerIntegrationAgent

draft = BrokerIntegrationAgent().generate(
    broker_slug="example_broker",
    provider_name="Example Broker",
    api_docs="Paste at least 80 characters of official API documentation here...",
)
print(draft.as_dict())
```

## Safety and limits

- The agent returns drafts only. It never writes files, imports generated modules, runs generated code, changes broker status, opens PRs, deploys, or places orders.
- `apps/brokers/integration_validation.py` performs static preflight checks for Python syntax, the base adapter import/subclass, disallowed paths, high-risk imports and dynamic execution calls, file-size limits, and likely hard-coded credentials. Its report is advisory defense-in-depth, not a sandbox or proof of safety.
- A failed preflight must block promotion to further automated testing; a passed preflight still requires isolated CI execution, review, and provider sandbox validation.
- Only `adapter.py`, `test_adapter_contract.py`, and `README.md` are allowed as generated draft paths.
- No credentials or account data should be supplied as input. Requests use `store: false`; provider docs are still sent to the configured OpenAI API, so submit only material you're permitted to share.
- Missing provider facts must remain explicit TODOs/questions; never invent endpoints or assume an undocumented protocol.
- Existing risk checks, live-trading configuration, idempotency, and trade reconciliation remain authoritative. Unknown execution state must be reconciled before retrying an order.
- Do not automatically enable live trading based on generated code or a green unit-test run.
- This feature is not a guarantee of production readiness or proof of live-provider compatibility.

## Verification checklist per provider

- Official API/auth docs and account permissions reviewed.
- OAuth redirect URIs/scopes or API-key scopes confirmed by an authorized operator.
- Secrets are stored in the secret manager and never logged or committed.
- Contract tests cover every abstract adapter method and unsupported capabilities fail explicitly.
- Provider-specific unit tests cover pagination, timeouts, throttling, malformed responses, reconnects, and auth expiry.
- Order tests cover idempotency and the ambiguous-timeout case without resubmitting an order.
- Demo/sandbox tests validate account identity, quote freshness, precision, minimum size, order status, fills, fees, and cancellation.
- Full CI passes; security review and human approval are recorded before production registration.
- Production onboarding docs accurately identify which providers have been verified.
