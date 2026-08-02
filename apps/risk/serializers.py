from rest_framework import serializers
from .models import RiskProfile,RiskRule,RiskAssessment,Exposure,DrawdownHistory,KillSwitchEvent
class RiskProfileSerializer(serializers.ModelSerializer):
    class Meta: model=RiskProfile; fields='__all__'; read_only_fields=('user','created_at')
class RiskRuleSerializer(serializers.ModelSerializer):
    class Meta: model=RiskRule; fields='__all__'
class RiskAssessmentSerializer(serializers.ModelSerializer):
    class Meta: model=RiskAssessment; fields='__all__'
class ExposureSerializer(serializers.ModelSerializer):
    class Meta: model=Exposure; fields='__all__'
class DrawdownHistorySerializer(serializers.ModelSerializer):
    class Meta: model=DrawdownHistory; fields='__all__'
class KillSwitchEventSerializer(serializers.ModelSerializer):
    class Meta: model=KillSwitchEvent; fields='__all__'
