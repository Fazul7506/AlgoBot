# Broker integration management workflow

The staff-only Django admin surface is available at `/admin/brokers/broker/integration-management/` to users permitted to access the Broker admin.

## Truthful status and merge criteria

- Broker catalog entries and `metadata.adapter_state` labels are descriptive only; they are not proof an adapter is production-ready.
- A provider integration PR should identify the provider in its title/body and include adapter code, provider configuration, tests, capability matrix, and validation evidence.
- Reviewers can request changes in PR discussion; the integration agent should commit fixes to the same provider-specific branch.
- Merge only after required CI checks pass on the latest head commit and repository branch-protection requirements are satisfied. Do not add a separate approval gate beyond repository policy.
- Never store broker secrets, GitHub tokens, or provider credentials in PR descriptions, logs, or the dashboard.

## Backend integrations still required

The existing broker models do not provide persistent user broker-addition requests, durable agent runs, live GitHub PR/check synchronization, or a secured LLM/code-generation service. These require models and migrations, authenticated endpoints, background execution, and configured secrets. The dashboard explicitly does not fabricate request records, PR numbers, test results, or merge readiness.
