from rest_framework.routers import DefaultRouter
from .views import RiskProfileViewSet,RiskRuleViewSet,RiskAssessmentViewSet,ExposureViewSet,DrawdownViewSet,KillSwitchViewSet
router=DefaultRouter(); router.register('risk/profile',RiskProfileViewSet,basename='risk-profile'); router.register('risk/rules',RiskRuleViewSet,basename='risk-rules'); router.register('risk/exposure',ExposureViewSet,basename='risk-exposure'); router.register('risk/drawdown',DrawdownViewSet,basename='risk-drawdown'); router.register('risk/assessment',RiskAssessmentViewSet,basename='risk-assessment'); router.register('risk/kill-switch',KillSwitchViewSet,basename='risk-kill-switch')
urlpatterns=router.urls
