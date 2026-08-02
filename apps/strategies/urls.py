from rest_framework.routers import DefaultRouter
from .views import StrategyViewSet
router=DefaultRouter(); router.register(r'strategies', StrategyViewSet, basename='strategy-engine')
urlpatterns=router.urls
