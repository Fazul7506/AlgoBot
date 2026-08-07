from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .allocation import AllocationService
from .engine import PortfolioEngine
from .models import CashFlow, Portfolio, PortfolioAllocation, PortfolioExposure, PortfolioForecast, PortfolioPerformance
from .serializers import CashFlowSerializer, PortfolioAllocationSerializer, PortfolioExposureSerializer, PortfolioForecastSerializer, PortfolioPerformanceSerializer, PortfolioSerializer


class PortfolioViewSet(viewsets.ModelViewSet):
    serializer_class = PortfolioSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Portfolio.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["get"])
    def dashboard(self, request, pk=None):
        return Response(PortfolioEngine().dashboard(self.get_object()))

    @action(detail=True, methods=["post"])
    def rebalance(self, request, pk=None):
        return Response({"suggestions": PortfolioEngine().rebalancing.suggestions(self.get_object())})

    @action(detail=True, methods=["post"])
    def allocate(self, request, pk=None):
        allocations = AllocationService().allocate(self.get_object(), request.data.get("targets", []), request.data.get("method", "percentage"))
        return Response(PortfolioAllocationSerializer(allocations, many=True).data)


class PortfolioPerformanceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PortfolioPerformanceSerializer
    def get_queryset(self): return PortfolioPerformance.objects.filter(portfolio__user=self.request.user)
class PortfolioAllocationViewSet(viewsets.ModelViewSet):
    serializer_class = PortfolioAllocationSerializer
    def get_queryset(self): return PortfolioAllocation.objects.filter(portfolio__user=self.request.user)
class PortfolioExposureViewSet(viewsets.ModelViewSet):
    serializer_class = PortfolioExposureSerializer
    def get_queryset(self): return PortfolioExposure.objects.filter(portfolio__user=self.request.user)
class PortfolioForecastViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PortfolioForecastSerializer
    def get_queryset(self): return PortfolioForecast.objects.filter(portfolio__user=self.request.user)
class CashFlowViewSet(viewsets.ModelViewSet):
    serializer_class = CashFlowSerializer
    def get_queryset(self): return CashFlow.objects.filter(portfolio__user=self.request.user)
