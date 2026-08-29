import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Register and verify the AlgoBot Telegram webhook and commands."

    def handle(self, *args, **options):
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        mode = str(getattr(settings, "TELEGRAM_MODE", "webhook") or "webhook").lower()
        base_url = getattr(settings, "BASE_URL", "").rstrip("/")
        webhook_url = getattr(settings, "TELEGRAM_WEBHOOK_URL", "") or f"{base_url}/api/notifications/telegram/webhook/"
        secret = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "")
        if mode != "webhook":
            self.stdout.write(self.style.WARNING("Telegram webhook registration skipped because TELEGRAM_MODE is not webhook."))
            return
        if not token or not secret or not webhook_url.startswith("https://"):
            self.stdout.write(self.style.WARNING("Telegram webhook registration skipped: token, secret and HTTPS webhook URL are required."))
            return

        api = f"https://api.telegram.org/bot{token}"
        commands = [
            {"command": "start", "description": "Connect or verify your Telegram account"},
            {"command": "status", "description": "Check Telegram connection status"},
            {"command": "account", "description": "Check linked AlgoBot account"},
            {"command": "alerts", "description": "View notification status"},
            {"command": "help", "description": "Show available commands"},
        ]
        last_error = None
        for attempt in range(3):
            try:
                me = requests.post(f"{api}/getMe", timeout=10)
                me.raise_for_status()
                if not me.json().get("ok"):
                    raise RuntimeError(me.json().get("description", "Telegram getMe failed"))
                response = requests.post(f"{api}/setWebhook", json={"url": webhook_url, "secret_token": secret, "allowed_updates": ["message"], "drop_pending_updates": False, "max_connections": 40}, timeout=15)
                response.raise_for_status()
                payload = response.json()
                if not payload.get("ok"):
                    raise RuntimeError(payload.get("description") or "Telegram rejected the webhook configuration.")
                cmd_response = requests.post(f"{api}/setMyCommands", json={"commands": commands}, timeout=10)
                cmd_response.raise_for_status()
                if not cmd_response.json().get("ok"):
                    raise RuntimeError(cmd_response.json().get("description", "Telegram rejected bot commands."))
                info = requests.post(f"{api}/getWebhookInfo", timeout=10)
                info.raise_for_status()
                info_payload = info.json().get("result") or {}
                if info_payload.get("url") != webhook_url:
                    raise RuntimeError("Telegram accepted setWebhook but getWebhookInfo returned a different URL.")
                self.stdout.write(self.style.SUCCESS(f"Telegram webhook healthy: {webhook_url}"))
                self.stdout.write(self.style.SUCCESS("Telegram commands registered: /start /status /account /alerts /help"))
                return
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2 ** attempt)
        self.stdout.write(self.style.WARNING(f"Telegram webhook registration did not complete: {last_error}"))
