from django.conf import settings
from django.db import models
from django.utils import timezone
from . import constants as c

class Tenant(models.Model):
    name=models.CharField(max_length=180); slug=models.SlugField(unique=True); status=models.CharField(max_length=32,default="trial",choices=[(x,x.title()) for x in c.TENANT_STATUSES]); owner=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,related_name="owned_tenants"); timezone=models.CharField(max_length=64,default="UTC"); currency=models.CharField(max_length=3,default="USD"); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: indexes=[models.Index(fields=["slug","status"])]
    def __str__(self): return self.name
class Organization(models.Model):
    tenant=models.ForeignKey(Tenant,on_delete=models.CASCADE,related_name="organizations"); name=models.CharField(max_length=180); industry=models.CharField(max_length=120,blank=True); country=models.CharField(max_length=80,blank=True); website=models.URLField(blank=True); logo=models.URLField(blank=True); status=models.CharField(max_length=32,default="active")
    class Meta: unique_together=("tenant","name")
class Workspace(models.Model):
    organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name="workspaces"); name=models.CharField(max_length=180); environment=models.CharField(max_length=32,default="production"); default_broker=models.CharField(max_length=80,blank=True); timezone=models.CharField(max_length=64,default="UTC")
class Subscription(models.Model):
    tenant=models.OneToOneField(Tenant,on_delete=models.CASCADE,related_name="subscription"); plan=models.CharField(max_length=32,default="free",choices=[(x,x.title()) for x in c.SUBSCRIPTION_PLANS]); status=models.CharField(max_length=32,default="trial"); billing_cycle=models.CharField(max_length=32,default="monthly",choices=[(x,x.title()) for x in c.BILLING_CYCLES]); price=models.DecimalField(max_digits=12,decimal_places=2,default=0); renewal_date=models.DateField(null=True,blank=True); trial_end=models.DateTimeField(null=True,blank=True)
class License(models.Model):
    subscription=models.OneToOneField(Subscription,on_delete=models.CASCADE,related_name="license"); license_key=models.CharField(max_length=80,unique=True); max_users=models.PositiveIntegerField(default=1); max_brokers=models.PositiveIntegerField(default=1); max_strategies=models.PositiveIntegerField(default=1); expires_at=models.DateTimeField(null=True,blank=True)
    @property
    def is_active(self): return self.expires_at is None or self.expires_at>timezone.now()
class Team(models.Model):
    organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name="teams"); name=models.CharField(max_length=120); description=models.TextField(blank=True)
class TeamMember(models.Model):
    team=models.ForeignKey(Team,on_delete=models.CASCADE,related_name="members"); user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE); role=models.CharField(max_length=32,choices=[(x,x.title()) for x in c.ROLES]); joined_at=models.DateTimeField(auto_now_add=True)
    class Meta: unique_together=("team","user")
class FeatureFlag(models.Model):
    feature=models.CharField(max_length=64,choices=[(x,x.replace('_',' ').title()) for x in c.FEATURES]); enabled=models.BooleanField(default=False); plan=models.CharField(max_length=32,blank=True); tenant=models.ForeignKey(Tenant,on_delete=models.CASCADE,null=True,blank=True,related_name="feature_flags")
class UsageMetric(models.Model):
    tenant=models.ForeignKey(Tenant,on_delete=models.CASCADE,related_name="usage_metrics"); metric=models.CharField(max_length=64,choices=[(x,x.replace('_',' ').title()) for x in c.USAGE_METRICS]); usage=models.BigIntegerField(default=0); quota=models.BigIntegerField(default=0); period=models.CharField(max_length=32,default="monthly")
    class Meta: unique_together=("tenant","metric","period")
class WhiteLabelSettings(models.Model):
    tenant=models.OneToOneField(Tenant,on_delete=models.CASCADE,related_name="branding"); brand_name=models.CharField(max_length=120,blank=True); logo=models.URLField(blank=True); custom_domain=models.CharField(max_length=255,blank=True); colors=models.JSONField(default=dict,blank=True); email_templates=models.JSONField(default=dict,blank=True)
