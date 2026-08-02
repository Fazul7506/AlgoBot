from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from trading.services.notification_service import NotificationService

class Command(BaseCommand):
    help = 'Send a test notification to the specified user (by username).'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username to send test notification to')
        parser.add_argument('--type', type=str, default='trade_opened', help='Alert type (trade_opened|trade_closed|profit_target|drawdown_warning)')
        parser.add_argument('--channels', type=str, help='Comma-separated channels (email,telegram,push)')

    def handle(self, *args, **options):
        username = options['username']
        alert_type = options['type']
        channels = None
        if options.get('channels'):
            channels = [c.strip() for c in options['channels'].split(',')]

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'User {username} not found'))
            return

        svc = NotificationService(user=user)
        result = svc.send(alert_type, details={'symbol': 'R_75', 'strategy': 'test'}, channels=channels)
        self.stdout.write(self.style.SUCCESS(f'Sent: {result}'))
