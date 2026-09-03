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
    def upgrade(self,tenant,plan,billing_cycle='monthly',price=0): return Subscription.objects.update_or_create(tenant=tenant,defaults={'plan':plan,'billing_cycle':billing_cycle,'price':price,'status':'active'})[0]
class BillingService:
    providers=('intasend','pesapal')
    def create_invoice(self,subscription,amount): return {'tenant_id':subscription.tenant_id,'amount':str(amount),'status':'open'}
    def pay(self,provider,amount,metadata=None): return {'provider':provider,'amount':str(amount),'status':'succeeded','metadata':metadata or {}}
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
