from rest_framework import serializers
from .models import CashFlow, Portfolio, PortfolioAccount, PortfolioAllocation, PortfolioExposure, PortfolioForecast, PortfolioPerformance


class PortfolioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Portfolio
        fields = "__all__"
        read_only_fields = ("user", "net_asset_value", "created_at", "updated_at")


class PortfolioAccountSerializer(serializers.ModelSerializer):
    class Meta: model = PortfolioAccount; fields = "__all__"

    def validate_portfolio(self, portfolio):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or portfolio.user_id != user.id:
            raise serializers.ValidationError("The selected portfolio does not belong to the authenticated user.")
        return portfolio


class PortfolioAllocationSerializer(serializers.ModelSerializer):
    class Meta: model = PortfolioAllocation; fields = "__all__"

    def validate_portfolio(self, portfolio):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or portfolio.user_id != user.id:
            raise serializers.ValidationError("The selected portfolio does not belong to the authenticated user.")
        return portfolio


class PortfolioPerformanceSerializer(serializers.ModelSerializer):
    class Meta: model = PortfolioPerformance; fields = "__all__"


class PortfolioExposureSerializer(serializers.ModelSerializer):
    class Meta: model = PortfolioExposure; fields = "__all__"

    def validate_portfolio(self, portfolio):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or portfolio.user_id != user.id:
            raise serializers.ValidationError("The selected portfolio does not belong to the authenticated user.")
        return portfolio


class PortfolioForecastSerializer(serializers.ModelSerializer):
    class Meta: model = PortfolioForecast; fields = "__all__"; read_only_fields = "__all__"


class CashFlowSerializer(serializers.ModelSerializer):
    class Meta: model = CashFlow; fields = "__all__"

    def validate_portfolio(self, portfolio):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or portfolio.user_id != user.id:
            raise serializers.ValidationError("The selected portfolio does not belong to the authenticated user.")
        return portfolio
