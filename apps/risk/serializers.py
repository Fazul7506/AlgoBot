from rest_framework import serializers
from .models import RiskProfile,RiskRule,RiskAssessment,Exposure,DrawdownHistory

class RiskProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model=RiskProfile
        fields='__all__'
        read_only_fields=('user','created_at')

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
