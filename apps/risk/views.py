from rest_framework import viewsets,permissions,decorators,response
from .models import RiskProfile,RiskRule,RiskAssessment,Exposure,DrawdownHistory,KillSwitchEvent
from .serializers import *
from .services import KillSwitchService
class OwnQuerysetMixin:
    permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return self.queryset.filter(user=self.request.user) if hasattr(self.queryset.model,'user') else self.queryset.filter(profile__user=self.request.user)
class RiskProfileViewSet(OwnQuerysetMixin,viewsets.ModelViewSet):
    queryset=RiskProfile.objects.all(); serializer_class=RiskProfileSerializer
    def perform_create(self,serializer): serializer.save(user=self.request.user)
class RiskRuleViewSet(OwnQuerysetMixin,viewsets.ModelViewSet): queryset=RiskRule.objects.select_related('profile'); serializer_class=RiskRuleSerializer
class RiskAssessmentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=RiskAssessmentSerializer; permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self): return RiskAssessment.objects.filter(trade__user=self.request.user)
class ExposureViewSet(OwnQuerysetMixin,viewsets.ReadOnlyModelViewSet): queryset=Exposure.objects.all(); serializer_class=ExposureSerializer
class DrawdownViewSet(OwnQuerysetMixin,viewsets.ReadOnlyModelViewSet): queryset=DrawdownHistory.objects.all(); serializer_class=DrawdownHistorySerializer
class KillSwitchViewSet(OwnQuerysetMixin,viewsets.ReadOnlyModelViewSet):
    queryset=KillSwitchEvent.objects.all(); serializer_class=KillSwitchEventSerializer
    @decorators.action(detail=False,methods=['post'],url_path='activate')
    def activate(self,request):
        event=KillSwitchService().activate(request.user,request.data.get('reason','Manual activation'),request.user); return response.Response(self.get_serializer(event).data)
    @decorators.action(detail=False,methods=['post'],url_path='deactivate')
    def deactivate(self,request): KillSwitchService().deactivate(request.user); return response.Response({'resolved':True})
