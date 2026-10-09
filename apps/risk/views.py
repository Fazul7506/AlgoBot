from rest_framework import viewsets, permissions, response
from .models import RiskProfile, RiskRule, RiskAssessment, Exposure, DrawdownHistory
from django.db.models import Q
from .serializers import *


class OwnQuerysetMixin:
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = self.queryset
        if hasattr(queryset.model, "user"):
            return queryset.filter(user=self.request.user)
        return queryset.filter(profile__user=self.request.user)


class RiskProfileViewSet(OwnQuerysetMixin, viewsets.ModelViewSet):
    queryset = RiskProfile.objects.all()
    serializer_class = RiskProfileSerializer

    def get_queryset(self):
        return super().get_queryset().order_by("-created_at")

    def list(self, request, *args, **kwargs):
        # The browser risk panel is a single-profile editor. Select a stable
        # existing profile rather than get_or_create(), which raises if older
        # accounts already have multiple profiles.
        profile = RiskProfile.objects.filter(user=request.user).order_by("created_at", "id").first()
        if profile is None:
            profile = RiskProfile.objects.create(
                user=request.user,
                profile_name="Default Risk Profile",
                risk_level="moderate",
                max_risk_per_trade=0.02,
                max_daily_loss=0.04,
                max_drawdown=0.10,
                max_open_positions=10,
                max_exposure=0.35,
            )
        serializer = self.get_serializer(profile)
        return response.Response([serializer.data])

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class RiskRuleViewSet(OwnQuerysetMixin, viewsets.ModelViewSet):
    queryset = RiskRule.objects.select_related("profile")
    serializer_class = RiskRuleSerializer


class RiskAssessmentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RiskAssessmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return RiskAssessment.objects.filter(
            Q(trade__user=self.request.user) | Q(broker_trade__user=self.request.user)
        ).order_by("-assessment_time").distinct()


class ExposureViewSet(OwnQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Exposure.objects.all()
    serializer_class = ExposureSerializer

    def get_queryset(self):
        return super().get_queryset().order_by("-updated_at")


class DrawdownViewSet(OwnQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = DrawdownHistory.objects.all()
    serializer_class = DrawdownHistorySerializer

    def get_queryset(self):
        return super().get_queryset().order_by("-timestamp")
