from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter
from .api import CashFlowViewSet, PortfolioAllocationViewSet, PortfolioExposureViewSet, PortfolioForecastViewSet, PortfolioPerformanceViewSet, PortfolioViewSet
from .analytics import AnalyticsService
from .benchmark import BenchmarkService
from .correlation import CorrelationService
from .diversification import DiversificationService
from .reporting import ReportingService

router = DefaultRouter()
router.register(r"portfolio", PortfolioViewSet, basename="portfolio")
router.register(r"portfolio/performance", PortfolioPerformanceViewSet, basename="portfolio-performance")
router.register(r"portfolio/allocation", PortfolioAllocationViewSet, basename="portfolio-allocation")
router.register(r"portfolio/exposure", PortfolioExposureViewSet, basename="portfolio-exposure")
router.register(r"portfolio/forecast", PortfolioForecastViewSet, basename="portfolio-forecast")
router.register(r"portfolio/cashflow", CashFlowViewSet, basename="portfolio-cashflow")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def diversification(request):
    return Response(DiversificationService().analyze([]))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def correlation(request):
    return Response(CorrelationService().matrix({}))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports(request):
    return Response({"report_types": ["daily", "weekly", "monthly", "quarterly", "yearly", "executive", "investor", "risk", "tax"], "formats": ["pdf", "excel", "csv", "json"]})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def benchmark(request):
    return Response(BenchmarkService().compare(0, 0))

urlpatterns = [
    path("", include(router.urls)),
    path("portfolio/diversification/", diversification, name="portfolio-diversification"),
    path("portfolio/correlation/", correlation, name="portfolio-correlation"),
    path("portfolio/reports/", reports, name="portfolio-reports"),
    path("portfolio/benchmark/", benchmark, name="portfolio-benchmark"),
]
