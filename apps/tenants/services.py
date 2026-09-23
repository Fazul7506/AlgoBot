from dataclasses import dataclass
from django.utils.crypto import get_random_string
from .models import Tenant, Organization, Workspace, Subscription, License, FeatureFlag, UsageMetric, Team, WhiteLabelSettings
from .exceptions import QuotaExceeded

class TenantEngine:
    def create_tenant(self,name,owner=None,slug=None,**kw): return Tenant.objects.create(name=name,owner=owner,slug=slug or name.lower().replace(' ','-'),**kw)
    def scope_queryset(self,qs,tenant): return qs.filter(tenant=tenant)
class OrganizationService:
    def create(self,tenant,name,**kw): return Organization.objects.create(tenant=tenant,name=name,**kw)
class WorkspaceService:
    def create(self,organization,name,**kw): return Workspace.objects.create(organization=organization,name=name,**kw)
class SubscriptionService:
    """Projection helper; payment authority lives in core billing."""
    PLAN_MAP = {"FREE": "free", "BASIC": "starter", "PRO": "professional", "ENTERPRISE": "enterprise"}

    def sync_from_core(self, tenant, core_subscription):
        from decimal import Decimal
        plan = self.PLAN_MAP.get(str(core_subscription.plan).upper(), "free")
        return Subscription.objects.update_or_create(
            tenant=tenant,
            defaults={
                "plan": plan,
                "status": "active" if core_subscription.is_active else "expired",
                "billing_cycle": "monthly",
                "price": Decimal(core_subscription.price_cents or 0) / Decimal("100"),
                "renewal_date": core_subscription.expires_at.date() if core_subscription.expires_at else None,
                "trial_end": None,
            },
        )[0]
class LicenseService:
    def issue(self,subscription,**limits): return License.objects.update_or_create(subscription=subscription,defaults={'license_key':get_random_string(32),**limits})[0]
class RBACService:
    role_permissions={'platform_owner':'*','organization_owner':'*','administrator':'*','viewer':'reports'}
    def has_permission(self,role,permission): return self.role_permissions.get(role)=='*' or permission in str(self.role_permissions.get(role,''))
class FeatureFlagService:
    def enabled(self,feature,tenant=None,plan=''): return FeatureFlag.objects.filter(feature=feature,enabled=True).filter(tenant=tenant).exists() or FeatureFlag.objects.filter(feature=feature,enabled=True,plan=plan).exists()
class QuotaService:
    def enforce(self,tenant,metric,increment=1,period='monthly'):
        obj,_=UsageMetric.objects.get_or_create(tenant=tenant,metric=metric,period=period,defaults={'quota':0});
        if obj.quota and obj.usage+increment>obj.quota: raise QuotaExceeded(metric)
        obj.usage+=increment; obj.save(update_fields=['usage']); return obj
class InvitationService:
    def invite(self,email,team,role='viewer'): return {'email':email,'team_id':team.id,'role':role,'status':'pending'}
class WhiteLabelService:
    def configure(self,tenant,**branding): return WhiteLabelSettings.objects.update_or_create(tenant=tenant,defaults=branding)[0]
