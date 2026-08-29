import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Register the AlgoBot Telegram bot webhook using production settings."

    def handle(self, *args, **options):
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        base_url = getattr(settings, "BASE_URL", "").rstrip("/")
        secret = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "")
        if not token:
            raise CommandError("TELEGRAM_BOT_TOKEN is not configured.")
        if not base_url.startswith("https://"):
            raise CommandError("BASE_URL must be an HTTPS production URL.")
        if not secret:
            raise CommandError("TELEGRAM_WEBHOOK_SECRET is not configured.")

        webhook_url = f"{base_url}/api/notifications/telegram/webhook/"
        api_url = f"https://api.telegram.org/bot{token}/setWebhook"
        try:
            response = requests.post(
                api_url,
                json={
                    "url": webhook_url,
                    "secret_token": secret,
                    "allowed_updates": ["message"],
                    "drop_pending_updates": False,
                },
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise CommandError(f"Telegram webhook registration failed: {exc}") from exc
        except ValueError as exc:
            raise CommandError("Telegram returned an invalid webhook response.") from exc

        if not payload.get("ok"):
            raise CommandError(payload.get("description") or "Telegram rejected the webhook configuration.")

        self.stdout.write(self.style.SUCCESS(f"Telegram webhook registered: {webhook_url}"))
