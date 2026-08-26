from django.db import transaction
from rest_framework import viewsets, permissions, decorators, response
from .models import RiskProfile, RiskRule, RiskAssessment, Exposure, DrawdownHistory, KillSwitchEvent
from .serializers import *
from .services import KillSwitchService


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
        # A newly connected account should always have a usable protection
        # profile.  Do this lazily so existing production databases need no
        # manual seed/migration step.
        profile, _ = RiskProfile.objects.get_or_create(
            user=request.user,
            defaults={
                "profile_name": "Default Risk Profile",
                "risk_level": "moderate",
                "max_risk_per_trade": 0.02,
                "max_daily_loss": 0.04,
                "max_drawdown": 0.10,
                "max_open_positions": 10,
                "max_exposure": 0.35,
            },
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
        return RiskAssessment.objects.filter(trade__user=self.request.user).order_by("-assessment_time")


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


class KillSwitchViewSet(OwnQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = KillSwitchEvent.objects.all()
    serializer_class = KillSwitchEventSerializer

    @decorators.action(detail=False, methods=["post"], url_path="activate")
    @transaction.atomic
    def activate(self, request):
        event = KillSwitchService().activate(
            request.user,
            request.data.get("reason", "Manual activation"),
            request.user,
        )
        return response.Response(self.get_serializer(event).data)

    @decorators.action(detail=False, methods=["post"], url_path="deactivate")
    def deactivate(self, request):
        KillSwitchService().deactivate(request.user)
        return response.Response({"resolved": True})
