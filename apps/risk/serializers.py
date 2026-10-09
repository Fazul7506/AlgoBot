from rest_framework import serializers
from .models import RiskProfile,RiskRule,RiskAssessment,Exposure,DrawdownHistory

class RiskProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model=RiskProfile
        fields='__all__'
        read_only_fields=('user','created_at')
        extra_kwargs = {
            "max_open_positions": {"min_value": 1},
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        for field in ("max_risk_per_trade", "max_daily_loss", "max_daily_profit", "max_drawdown", "max_exposure"):
            value = attrs.get(field, getattr(self.instance, field, None))
            if value is not None and (value < 0 or value > 1):
                raise serializers.ValidationError({field: "Value must be between 0 and 1 (a fraction of account equity)."})
        return attrs

class RiskRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model=RiskRule
        fields='__all__'

    def validate_profile(self, profile):
        request=self.context.get('request')
        user=getattr(request,'user',None)
        if not user or not user.is_authenticated or profile.user_id != user.id:
            raise serializers.ValidationError('The selected risk profile does not belong to the authenticated user.')
        return profile

    def validate(self, attrs):
        attrs = super().validate(attrs)
        value = attrs.get("value", getattr(self.instance, "value", None))
        rule_type = attrs.get("rule_type", getattr(self.instance, "rule_type", ""))
        if value is not None and value < 0:
            raise serializers.ValidationError({"value": "Risk rule values cannot be negative."})
        fractional_rules = {
            "max_risk_per_trade", "max_daily_loss", "max_daily_profit",
            "max_weekly_loss", "max_monthly_loss", "max_drawdown",
            "max_symbol_exposure", "max_market_exposure", "max_broker_exposure",
        }
        if value is not None and rule_type in fractional_rules and value > 1:
            raise serializers.ValidationError({"value": "This risk rule must be a fraction between 0 and 1."})
        count_rules = {"max_open_positions", "max_simultaneous_strategies", "max_consecutive_losses", "max_consecutive_wins"}
        if value is not None and rule_type in count_rules and value != value.to_integral_value():
            raise serializers.ValidationError({"value": "This risk rule must be a whole number."})
        return attrs

class RiskAssessmentSerializer(serializers.ModelSerializer):
    class Meta:
        model=RiskAssessment
        fields='__all__'

class ExposureSerializer(serializers.ModelSerializer):
    class Meta:
        model=Exposure
        fields='__all__'

class DrawdownHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model=DrawdownHistory
        fields='__all__'
        read_only_fields='__all__'
