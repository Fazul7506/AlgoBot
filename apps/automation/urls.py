from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .api import WorkflowViewSet, EventViewSet, RuleViewSet, HistoryViewSet, execute, schedule, approve
router=DefaultRouter(); router.register("automation/workflows",WorkflowViewSet,basename="automation-workflows"); router.register("automation/events",EventViewSet,basename="automation-events"); router.register("automation/rules",RuleViewSet,basename="automation-rules"); router.register("automation/history",HistoryViewSet,basename="automation-history")
urlpatterns=[path("",include(router.urls)),path("automation/execute/",execute),path("automation/schedule/",schedule),path("automation/approve/",approve)]
