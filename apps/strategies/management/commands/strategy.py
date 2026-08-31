import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.contrib.auth import get_user_model

from apps.brokers.models import BrokerAccount
from apps.strategies.models import Strategy, StrategyConfiguration


class Command(BaseCommand):
    help = 'Inspect and control the current AlgoBot strategy for a user.'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['list', 'current', 'switch', 'criteria'])
        parser.add_argument('--user', type=int, required=True, help='Django user id')
        parser.add_argument('--strategy', help='Strategy slug for switch')
        parser.add_argument('--configuration', type=int, help='StrategyConfiguration id')
        parser.add_argument('--criteria', help='Criteria JSON object for criteria action')

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(pk=options['user']).first()
        if not user:
            raise CommandError('User not found.')
        action = options['action']
        configs = StrategyConfiguration.objects.filter(user=user).select_related('strategy', 'broker_account', 'broker_account__broker')

        if action == 'list':
            self.stdout.write('AVAILABLE STRATEGIES:')
            for strategy in Strategy.objects.filter(enabled=True).order_by('name'):
                count = configs.filter(strategy=strategy).count()
                marker = '*' if configs.filter(strategy=strategy, is_active=True, enabled=True).exists() else ' '
                self.stdout.write(f' {marker} {strategy.slug} | {strategy.name} | configurations={count}')
            return

        if action == 'current':
            config = configs.filter(is_active=True, enabled=True).first()
            if not config:
                self.stdout.write('CURRENT STRATEGY: NONE')
                self.stdout.write('Configure a strategy, then run strategy switch --user <id> --strategy <slug>.')
                return
            account = config.broker_account
            self.stdout.write(f'CURRENT STRATEGY: {config.strategy.slug}')
            self.stdout.write(f'CONFIGURATION: {config.pk}')
            self.stdout.write(f'SYMBOL/TIMEFRAME: {config.symbol}/{config.timeframe}')
            self.stdout.write(f'BROKER ACCOUNT: {account.account_id if account else "NONE"}')
            self.stdout.write(f'CRITERIA: {json.dumps(config.criteria or {}, sort_keys=True)}')
            return

        if action == 'switch':
            slug = options.get('strategy')
            config_id = options.get('configuration')
            qs = configs.filter(enabled=True)
            if config_id:
                config = qs.filter(pk=config_id).first()
            elif slug:
                config = qs.filter(strategy__slug=slug).order_by('-updated_at').first()
            else:
                raise CommandError('Provide --strategy <slug> or --configuration <id>.')
            if not config:
                raise CommandError('No enabled configuration matches the requested strategy/configuration.')
            if not config.broker_account_id:
                raise CommandError('Selected strategy has no broker account. Configure it with an account first.')
            if config.broker_account.status != 'active':
                raise CommandError('Selected strategy broker account is not active.')
            with transaction.atomic():
                StrategyConfiguration.objects.select_for_update().filter(user=user, is_active=True).update(is_active=False)
                config.is_active = True
                config.save(update_fields=['is_active', 'updated_at'])
            self.stdout.write(self.style.SUCCESS(f'SWITCHED CURRENT STRATEGY: {config.strategy.slug} ({config.pk})'))
            return

        if action == 'criteria':
            config = configs.filter(pk=options.get('configuration')).first() if options.get('configuration') else configs.filter(is_active=True).first()
            if not config:
                raise CommandError('No selected configuration. Use --configuration or switch a current strategy first.')
            raw = options.get('criteria')
            if raw is None:
                self.stdout.write(json.dumps(config.criteria or {}, indent=2, sort_keys=True))
                return
            try:
                criteria = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise CommandError(f'Invalid criteria JSON: {exc}')
            if not isinstance(criteria, dict):
                raise CommandError('Criteria must be a JSON object.')
            config.criteria = criteria
            config.save(update_fields=['criteria', 'updated_at'])
            self.stdout.write(self.style.SUCCESS(f'CRITERIA UPDATED FOR CONFIGURATION {config.pk}'))
