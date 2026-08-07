from django.urls import path
from . import views
urlpatterns=[path("health/",views.health),path("status/",views.status),path("version/",views.version),path("deployment/",views.deployment),path("backups/",views.backups),path("rollback/",views.rollback),path("restore/",views.restore)]
