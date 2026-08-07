from django.urls import path
from . import views
urlpatterns = [path("keys/", views.keys), path("plugins/", views.plugins), path("plugins/install/", views.install_plugin), path("webhooks/", views.webhooks), path("sdk/", views.sdk), path("docs/", views.docs), path("sandbox/", views.sandbox)]
