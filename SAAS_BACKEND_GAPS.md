# SaaS Backend Audit — Phase 16

The tenant domain contains a strong domain model and service layer, but several areas remain intentionally incomplete and should not be represented as fully production-ready:

- `apps.tenants.api` is only a scaffold.
- `apps.tenants.urls` previously exposed no routes.
- Invitation service currently returns an in-memory pending object rather than persisting an invitation.
- Billing service currently returns simulated invoice/payment dictionaries; it is not a payment gateway implementation.
- RBAC is currently a minimal role map.
- Feature flags and quotas need tenant-aware enforcement at every protected feature boundary.
- White-label settings need an authenticated management UI and secure custom-domain verification.
- Usage metrics need event-driven increments from trading/API/AI/notification services.
- Subscription upgrades need real provider checkout, webhook reconciliation and idempotency before charging customers.

Phase 16 surfaces the working domain primitives without pretending those incomplete pieces are production payment/authentication infrastructure.
