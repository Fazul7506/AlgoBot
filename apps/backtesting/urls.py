from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import BacktestViewSet, StatisticsViewSet, paper_start, paper_stop, paper_account, optimization_start, optimization_results, replay
router=DefaultRouter(); router.register('backtests',BacktestViewSet,basename='backtests'); router.register('statistics',StatisticsViewSet,basename='statistics')
urlpatterns=[path('',include(router.urls)),path('paper/start/',paper_start),path('paper/stop/',paper_stop),path('paper/account/',paper_account),path('optimization/start/',optimization_start),path('optimization/results/',optimization_results),path('replay/',replay)]
