from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .constants import SUBSCRIPTION_PLANS, BILLING_CYCLES, ROLES
from .models import Tenant, Organization, Workspace, Subscription, License, Team, TeamMember, UsageMetric
from .services import TenantEngine, OrganizationService, WorkspaceService, SubscriptionService, LicenseService, InvitationService, QuotaService

def _tenant_for(user):
    tenant = Tenant.objects.filter(owner=user).prefetch_related(
        "organizations__workspaces",
        "subscription__license",
    ).first()
    if tenant:
        return tenant
    return Tenant.objects.filter(organizations__teams__members__user=user).distinct().first()

def _serialize_tenant(tenant):
    if not tenant:
        return None
    sub = getattr(tenant, "subscription", None)
    license_obj = getattr(sub, "license", None) if sub else None
    orgs = []
    for org in tenant.organizations.all():
        orgs.append({
            "id": org.id, "name": org.name, "industry": org.industry,
            "country": org.country, "status": org.status,
            "workspaces": [{"id": w.id, "name": w.name, "environment": w.environment,
                            "default_broker": w.default_broker, "timezone": w.timezone}
                           for w in org.workspaces.all()],
            "teams": [{"id": t.id, "name": t.name, "description": t.description,
                       "members": t.members.count()} for t in org.teams.all()],
        })
    usage = [{"metric": u.metric, "usage": u.usage, "quota": u.quota, "period": u.period}
             for u in tenant.usage_metrics.all()]
    return {
        "id": tenant.id, "name": tenant.name, "slug": tenant.slug,
        "status": tenant.status, "timezone": tenant.timezone, "currency": tenant.currency,
        "subscription": {
            "plan": sub.plan, "status": sub.status, "billing_cycle": sub.billing_cycle,
            "price": str(sub.price), "renewal_date": sub.renewal_date.isoformat() if sub.renewal_date else None,
            "trial_end": sub.trial_end.isoformat() if sub.trial_end else None,
        } if sub else None,
        "license": {
            "active": license_obj.is_active, "max_users": license_obj.max_users,
            "max_brokers": license_obj.max_brokers, "max_strategies": license_obj.max_strategies,
            "expires_at": license_obj.expires_at.isoformat() if license_obj.expires_at else None,
        } if license_obj else None,
        "organizations": orgs,
        "usage": usage,
    }

@login_required
@require_http_methods(["GET"])
def dashboard(request):
    tenant = _tenant_for(request.user)
    return JsonResponse({
        "tenant": _serialize_tenant(tenant),
        "plans": list(SUBSCRIPTION_PLANS),
        "billing_cycles": list(BILLING_CYCLES),
        "roles": list(ROLES),
    })

@login_required
@require_http_methods(["POST"])
def create_tenant(request):
    import json
    data=json.loads(request.body or "{}")
    name=str(data.get("name","")).strip()
    if not name:
        return JsonResponse({"error":"Tenant name is required."}, status=400)
    if Tenant.objects.filter(owner=request.user).exists():
        return JsonResponse({"error":"You already own a tenant."}, status=409)
    tenant=TenantEngine().create_tenant(name=name, owner=request.user, timezone=data.get("timezone","Africa/Nairobi"), currency=data.get("currency","USD"))
    Subscription.objects.create(tenant=tenant, plan="free", status="trial", billing_cycle="monthly", price=0)
    return JsonResponse({"tenant": _serialize_tenant(tenant)}, status=201)

@login_required
@require_http_methods(["POST"])
def create_organization(request):
    import json
    tenant=_tenant_for(request.user)
    if not tenant: return JsonResponse({"error":"Create or join a workspace first."}, status=400)
    data=json.loads(request.body or "{}"); name=str(data.get("name","")).strip()
    if not name: return JsonResponse({"error":"Organization name is required."}, status=400)
    org=OrganizationService().create(tenant, name, industry=data.get("industry",""), country=data.get("country",""), website=data.get("website",""))
    return JsonResponse({"organization":{"id":org.id,"name":org.name}} ,status=201)

@login_required
@require_http_methods(["POST"])
def create_workspace(request):
    import json
    tenant=_tenant_for(request.user)
    if not tenant: return JsonResponse({"error":"Create or join a tenant first."}, status=400)
    data=json.loads(request.body or "{}")
    try: org=tenant.organizations.get(id=int(data.get("organization_id")))
    except (TypeError, ValueError, Organization.DoesNotExist):
        return JsonResponse({"error":"Valid organization_id is required."}, status=400)
    name=str(data.get("name","")).strip()
    if not name: return JsonResponse({"error":"Workspace name is required."}, status=400)
    ws=WorkspaceService().create(org,name,environment=data.get("environment","production"),default_broker=data.get("default_broker",""),timezone=data.get("timezone",tenant.timezone))
    return JsonResponse({"workspace":{"id":ws.id,"name":ws.name,"environment":ws.environment}},status=201)

@login_required
@require_http_methods(["POST"])
def upgrade_subscription(request):
    import json
    tenant=_tenant_for(request.user)
    if not tenant: return JsonResponse({"error":"Tenant not found."}, status=400)
    data=json.loads(request.body or "{}"); plan=data.get("plan")
    if plan not in SUBSCRIPTION_PLANS: return JsonResponse({"error":"Unsupported subscription plan."}, status=400)
    cycle=data.get("billing_cycle","monthly")
    if cycle not in BILLING_CYCLES: return JsonResponse({"error":"Unsupported billing cycle."}, status=400)
    price=Decimal(str(data.get("price",0) or 0))
    sub=SubscriptionService().upgrade(tenant,plan,cycle,price)
    LicenseService().issue(sub,max_users=int(data.get("max_users",1)),max_brokers=int(data.get("max_brokers",1)),max_strategies=int(data.get("max_strategies",1)))
    return JsonResponse({"subscription":{"plan":sub.plan,"status":sub.status,"billing_cycle":sub.billing_cycle,"price":str(sub.price)}})

@login_required
@require_http_methods(["POST"])
def invite_member(request):
    import json
    tenant=_tenant_for(request.user)
    if not tenant: return JsonResponse({"error":"Tenant not found."}, status=400)
    data=json.loads(request.body or "{}"); email=str(data.get("email","")).strip()
    role=data.get("role","viewer")
    if not email: return JsonResponse({"error":"Email is required."}, status=400)
    if role not in ROLES: return JsonResponse({"error":"Unsupported role."}, status=400)
    org=tenant.organizations.first()
    if not org: return JsonResponse({"error":"Create an organization first."}, status=400)
    team=org.teams.first() or Team.objects.create(organization=org,name="Default Team")
    return JsonResponse(InvitationService().invite(email,team,role),status=201)
