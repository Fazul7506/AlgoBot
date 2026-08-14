from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="copy_dashboard_api"),
    path("subscribe/", views.subscribe, name="copy_subscribe_api"),
    path("pause/", views.pause, name="copy_pause_api"),
    path("resume/", views.resume, name="copy_resume_api"),
    path("stop/", views.stop, name="copy_stop_api"),
    path("risk/", views.risk_settings, name="copy_risk_api"),
    path("test/", views.test_copy, name="copy_test_api"),
]
