from django.utils import timezone
from .models import RiskProfile, RiskRule, RiskAssessment, Exposure, DrawdownHistory, KillSwitchEvent
from . import constants as c


class RiskRepository:
    def profile_for_user(self, user):
        profile, _ = RiskProfile.objects.get_or_create(user=user, defaults={'profile_name': 'Default Risk Profile'})
        return profile

    def apply_level_defaults(self, profile):
        if profile.risk_level in c.DEFAULT_PROFILE_LIMITS:
            vals = c.DEFAULT_PROFILE_LIMITS[profile.risk_level]
            profile.max_risk_per_trade, profile.max_daily_loss, profile.max_daily_profit, profile.max_drawdown, profile.max_open_positions, profile.max_exposure = vals
            profile.save()
        return profile

    def enabled_rules(self, profile):
        return profile.rules.filter(enabled=True).order_by('priority')

    def assess(self, trade, score, approved, reason='', adjusted=None):
        payload = {
            'risk_score': score,
            'approved': approved,
            'rejection_reason': reason,
            'adjusted_parameters': adjusted or {},
        }
        if trade.__class__.__module__.startswith('apps.brokers'):
            payload['broker_trade'] = trade
        else:
            payload['trade'] = trade
        return RiskAssessment.objects.create(**payload)

    def active_kill_switch(self, user):
        return KillSwitchEvent.objects.filter(user=user, resolved_at__isnull=True).first()

    def activate_kill_switch(self, user, reason, activated_by=None):
        return KillSwitchEvent.objects.create(user=user, reason=reason, activated_by=activated_by or user)

    def deactivate_kill_switch(self, user):
        return KillSwitchEvent.objects.filter(user=user, resolved_at__isnull=True).update(resolved_at=timezone.now())
