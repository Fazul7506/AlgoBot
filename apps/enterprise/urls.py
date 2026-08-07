from django.urls import path
from . import views
urlpatterns=[path("status/",views.status),path("agents/",views.agents),path("optimization/",views.optimization),path("optimize/",views.optimize),path("self-heal/",views.self_heal),path("governance/",views.governance),path("knowledge/",views.knowledge),path("executive/",views.executive)]
