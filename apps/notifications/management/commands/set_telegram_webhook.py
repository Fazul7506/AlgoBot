import requests
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Register the AlgoBot Telegram bot webhook using production settings."

    def handle(self, *args, **options):
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        base_url = getattr(settings, "BASE_URL", "").rstrip("/")
        secret = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "")

        # Builds must remain deploy-safe when Telegram is intentionally disabled.
        if not token or not secret or not base_url.startswith("https://"):
            self.stdout.write(
                self.style.WARNING(
                    "Telegram webhook registration skipped: production Telegram settings are not fully configured."
                )
            )
            return

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
            self.stdout.write(self.style.WARNING(f"Telegram webhook registration skipped: {exc}"))
            return
        except ValueError:
            self.stdout.write(self.style.WARNING("Telegram webhook registration skipped: invalid Telegram response."))
            return

        if not payload.get("ok"):
            self.stdout.write(
                self.style.WARNING(
                    payload.get("description") or "Telegram rejected the webhook configuration."
                )
            )
            return

        self.stdout.write(self.style.SUCCESS("Telegram webhook registered successfully."))
