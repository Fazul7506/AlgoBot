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

## Staff-driven draft PR and live check synchronization

The staff-only management page can create an integration request or ask the configured AI agent for a review-only provider draft. Configure `OPENAI_API_KEY` and `GITHUB_TOKEN` (repository Contents and Pull requests write permissions) in the deployment secret manager; optionally set `GITHUB_REPOSITORY` as `owner/name`. Do not put credentials in request fields or commit them. The agent performs static preflight before creating a provider-named **draft** pull request under `apps/brokers/integration_drafts/<provider_slug>/`. Generated source is not executed, imported into production, enabled, or merged.

Refresh actual GitHub pull-request and latest-head CI state by scheduling `python manage.py sync_broker_integration_runs` (for example, every 5 minutes in the deployment scheduler) with `GITHUB_TOKEN` configured. The page displays the last synchronized check state; until the command has run successfully, it does not imply that checks have passed. The command records the PR state, head SHA, check-run names/statuses/conclusions, combined commit status, failures, and conservative merge-readiness calculation. A passing synchronization is evidence for review only and does not bypass branch protection or human approval.
