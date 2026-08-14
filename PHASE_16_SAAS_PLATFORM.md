# Phase 16 — SaaS Platform

The existing tenant/subscription/organization/workspace backend was audited and surfaced in a real SaaS Control Center.

Backend models used:
- Tenant
- Organization
- Workspace
- Subscription
- License
- Team
- TeamMember
- FeatureFlag
- UsageMetric
- WhiteLabelSettings

New authenticated APIs:
- GET `/api/tenants/dashboard/`
- POST `/api/tenants/`
- POST `/api/tenants/organizations/`
- POST `/api/tenants/workspaces/`
- POST `/api/tenants/subscription/upgrade/`
- POST `/api/tenants/invitations/`

New page:
- `/saas/` -> SaaS Control Center

The UI exposes:
- tenant status
- subscription plan/status
- license limits
- organizations
- workspaces/environments
- usage and quotas
- team access
- plan selection
- organization creation
- tenant onboarding
- member invitations
- links into trading platform modules

Security:
- endpoints require authenticated sessions
- POST requests use Django CSRF protection
- tenant ownership scoping is applied to dashboard mutations
- payment provider names are presented as integrations; actual payment capture remains provider/backend controlled
