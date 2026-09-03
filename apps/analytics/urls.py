from django.urls import path
from . import views

urlpatterns = [
    path("", views.analytics_dashboard, name="analytics-dashboard"),
    path("data/", views.analysis_data, name="analysis-data"),
    path("markets/", views.analysis_markets, name="analysis-markets"),
    path("export/", views.analytics_export, name="analytics-export"),
]
