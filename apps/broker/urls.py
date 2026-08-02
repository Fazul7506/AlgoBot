from django.urls import path
from . import views
urlpatterns = [
 path("brokers/", views.brokers), path("brokers/accounts/", views.accounts), path("brokers/connect/", views.connect),
 path("brokers/disconnect/", views.disconnect), path("brokers/status/", views.status), path("brokers/health/", views.health),
]
