from django.urls import path
from .security_settings_api import security_alerts_api, trusted_device_detail_api, trusted_devices_api

urlpatterns = [
    path("alerts/", security_alerts_api, name="security-alerts-api"),
    path("trusted-devices/", trusted_devices_api, name="trusted-devices-api"),
    path("trusted-devices/<int:device_id>/", trusted_device_detail_api, name="trusted-device-detail-api"),
]
