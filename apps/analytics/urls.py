from django.urls import path
from . import views

urlpatterns = [
    path("", views.analytics_dashboard, name="analytics-dashboard"),
    path("export/", views.analytics_export, name="analytics-export"),
]
