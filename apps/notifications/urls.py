from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .api import NotificationViewSet, PreferenceViewSet, TemplateViewSet, DeliveryViewSet, send, broadcast, webhook
router=DefaultRouter(); router.register("notifications",NotificationViewSet,basename="enterprise-notifications"); router.register("notifications/preferences",PreferenceViewSet,basename="notification-preferences"); router.register("notifications/templates",TemplateViewSet,basename="notification-templates"); router.register("notifications/delivery",DeliveryViewSet,basename="notification-delivery")
urlpatterns=[path("",include(router.urls)),path("notifications/send/",send),path("notifications/broadcast/",broadcast),path("notifications/webhook/",webhook),path("notifications/history/",include(router.urls))]
