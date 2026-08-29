from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
import requests

class Command(BaseCommand):
    help = 'Register or replace the production Telegram webhook for AlgoBot.'

    def add_arguments(self, parser):
        parser.add_argument('--delete', action='store_true', help='Delete the configured Telegram webhook instead.')

    def handle(self, *args, **options):
        token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        secret = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '')
        base_url = getattr(settings, 'BASE_URL', '').rstrip('/')
        if not token:
            raise CommandError('TELEGRAM_BOT_TOKEN is not configured.')
        if options['delete']:
            response = requests.post(f'https://api.telegram.org/bot{token}/deleteWebhook', timeout=15)
        else:
            if not base_url.startswith('https://'):
                raise CommandError('BASE_URL must be an HTTPS production URL before registering the Telegram webhook.')
            webhook_url = f'{base_url}/api/notifications/telegram/webhook/'
            payload = {'url': webhook_url, 'allowed_updates': ['message'], 'drop_pending_updates': False}
            if secret:
                payload['secret_token'] = secret
            response = requests.post(f'https://api.telegram.org/bot{token}/setWebhook', json=payload, timeout=15)
        try:
            data = response.json()
        except ValueError:
            data = {}
        if not response.ok or not data.get('ok'):
            raise CommandError(f'Telegram webhook operation failed (HTTP {response.status_code}).')
        self.stdout.write(self.style.SUCCESS('Telegram webhook configured successfully.'))
