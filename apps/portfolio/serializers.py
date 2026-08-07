from rest_framework import serializers
from .models import CashFlow, Portfolio, PortfolioAccount, PortfolioAllocation, PortfolioExposure, PortfolioForecast, PortfolioPerformance


class PortfolioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Portfolio
        fields = "__all__"
        read_only_fields = ("user", "net_asset_value", "created_at", "updated_at")

class PortfolioAccountSerializer(serializers.ModelSerializer):
    class Meta: model = PortfolioAccount; fields = "__all__"
class PortfolioAllocationSerializer(serializers.ModelSerializer):
    class Meta: model = PortfolioAllocation; fields = "__all__"
class PortfolioPerformanceSerializer(serializers.ModelSerializer):
    class Meta: model = PortfolioPerformance; fields = "__all__"
class PortfolioExposureSerializer(serializers.ModelSerializer):
    class Meta: model = PortfolioExposure; fields = "__all__"
class PortfolioForecastSerializer(serializers.ModelSerializer):
    class Meta: model = PortfolioForecast; fields = "__all__"
class CashFlowSerializer(serializers.ModelSerializer):
    class Meta: model = CashFlow; fields = "__all__"
