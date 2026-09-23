from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="tenant_dashboard_api"),
    path("tenants/", views.create_tenant, name="tenant_create_api"),
    path("organizations/", views.create_organization, name="organization_create_api"),
    path("workspaces/", views.create_workspace, name="workspace_create_api"),
    path("invitations/", views.invite_member, name="tenant_invite_api"),
]
