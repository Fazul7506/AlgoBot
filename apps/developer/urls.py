from django.urls import path
from . import views

app_name = "developer"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("keys/", views.keys, name="keys"),
    path("keys/create/", views.key_create, name="key_create"),
    path("keys/<int:pk>/rotate/", views.key_rotate, name="key_rotate"),
    path("keys/<int:pk>/revoke/", views.key_revoke, name="key_revoke"),
    path("keys/<int:pk>/delete/", views.key_delete, name="key_delete"),
    path("plugins/", views.plugins, name="plugins"),
    path("plugins/install/", views.install_plugin, name="plugin_install"),
    path("webhooks/", views.webhooks, name="webhooks"),
    path("webhooks/create/", views.webhook_create, name="webhook_create"),
    path("webhooks/<int:pk>/test/", views.webhook_test, name="webhook_test"),
    path("sdk/", views.sdk, name="sdk"),
    path("docs/", views.docs, name="docs"),
    path("analytics/", views.analytics, name="analytics"),
    path("integrations/", views.integrations, name="integrations"),
    path("sandbox/", views.sandbox, name="sandbox"),
]
