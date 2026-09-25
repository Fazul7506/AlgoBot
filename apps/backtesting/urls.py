from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import BacktestViewSet, StatisticsViewSet, optimization_start, optimization_results, replay
router=DefaultRouter(); router.register('backtests',BacktestViewSet,basename='backtests'); router.register('statistics',StatisticsViewSet,basename='statistics')
urlpatterns=[path('',include(router.urls)),path('optimization/start/',optimization_start),path('optimization/results/',optimization_results),path('replay/',replay)]
