from django.urls import path
from . import views

app_name = "developer"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("api/explorer/", views.api_explorer, name="api_explorer"),
    path("api/status/", views.api_status, name="api_status"),
    # Browser management uses same-origin HTML forms + Django messages.
    path("browser/keys/create/", views.browser_key_create, name="browser_key_create"),
    path("browser/keys/<int:pk>/rotate/", views.browser_key_rotate, name="browser_key_rotate"),
    path("browser/keys/<int:pk>/revoke/", views.browser_key_revoke, name="browser_key_revoke"),
    path("browser/keys/<int:pk>/delete/", views.browser_key_delete, name="browser_key_delete"),
    path("browser/webhooks/create/", views.browser_webhook_create, name="browser_webhook_create"),
    path("browser/webhooks/<int:pk>/test/", views.browser_webhook_test, name="browser_webhook_test"),
    path("browser/sandbox/provision/", views.browser_sandbox_provision, name="browser_sandbox_provision"),
    # Machine/API clients retain their existing developer endpoints.
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
