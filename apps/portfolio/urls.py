from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from .api import (
    CashFlowViewSet,
    PortfolioAllocationViewSet,
    PortfolioExposureViewSet,
    PortfolioForecastViewSet,
    PortfolioPerformanceViewSet,
    PortfolioViewSet,
)
from .benchmark import BenchmarkService
from .correlation import CorrelationService
from .diversification import DiversificationService

router = DefaultRouter()
router.register(r"portfolio/performance", PortfolioPerformanceViewSet, basename="portfolio-performance")
router.register(r"portfolio/allocation", PortfolioAllocationViewSet, basename="portfolio-allocation")
router.register(r"portfolio/exposure", PortfolioExposureViewSet, basename="portfolio-exposure")
router.register(r"portfolio/forecast", PortfolioForecastViewSet, basename="portfolio-forecast")
router.register(r"portfolio/cashflow", CashFlowViewSet, basename="portfolio-cashflow")
router.register(r"portfolio", PortfolioViewSet, basename="portfolio")


def _portfolio_for_request(request):
    from .models import Portfolio

    portfolio_id = request.GET.get("portfolio_id")
    queryset = Portfolio.objects.filter(user=request.user, status="active")
    if portfolio_id:
        return queryset.filter(pk=portfolio_id).first()
    return queryset.first()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def diversification(request):
    portfolio = _portfolio_for_request(request)
    if portfolio is None:
        return Response({"status": "no_data", "reason": "No active portfolio is available for this account."})
    return Response(
        {
            "status": "ok",
            "portfolio_id": portfolio.pk,
            **DiversificationService().analyze(portfolio.allocations.all()),
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def correlation(request):
    # A correlation matrix requires time-series observations. The portfolio
    # schema does not contain a canonical asset-return series, so an empty
    # matrix is preferable to fabricating an identity/zero matrix.
    return Response(
        {
            "status": "no_data",
            "reason": "No canonical portfolio return series is available for correlation analysis.",
            "matrix": {},
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports(request):
    return Response(
        {
            "report_types": ["daily", "weekly", "monthly", "quarterly", "yearly", "executive", "investor", "risk", "tax"],
            "formats": ["pdf", "excel", "csv", "json"],
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def benchmark(request):
    portfolio_return = request.GET.get("portfolio_return")
    benchmark_return = request.GET.get("benchmark_return")
    if portfolio_return is None or benchmark_return is None:
        return Response(
            {
                "status": "no_data",
                "reason": "Portfolio and benchmark return observations are required.",
            }
        )
    try:
        result = BenchmarkService().compare(
            float(portfolio_return),
            float(benchmark_return),
            benchmark_name=request.GET.get("benchmark_name", "benchmark"),
        )
    except (TypeError, ValueError) as exc:
        return Response({"status": "error", "reason": str(exc)}, status=400)
    return Response({"status": "ok", **result})


urlpatterns = [
    path("portfolio/diversification/", diversification, name="portfolio-diversification"),
    path("portfolio/correlation/", correlation, name="portfolio-correlation"),
    path("portfolio/reports/", reports, name="portfolio-reports"),
    path("portfolio/benchmark/", benchmark, name="portfolio-benchmark"),
    path("", include(router.urls)),
]
