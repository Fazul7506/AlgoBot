import json
import logging
import os
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from django.conf import settings

from django.contrib.auth.models import User
from trading.models.notifications import Notification

logger = logging.getLogger(__name__)


class NotificationService:
    """Simple notification service for trade alerts and account events."""

    ALERT_TYPES = {
        'trade_opened': 'Trade opened',
        'trade_closed': 'Trade closed',
        'profit_target': 'Profit target reached',
        'drawdown_warning': 'Drawdown warning',
    }

    CHANNELS = ('email', 'telegram', 'push')

    def __init__(self, user: Optional[User] = None):
        self.user = user

    def build_message(self, alert_type: str, details: Optional[Dict[str, Any]] = None) -> str:
        details = details or {}
        base = self.ALERT_TYPES.get(alert_type, alert_type.replace('_', ' ').title())
        symbol = details.get('symbol') or 'N/A'
        strategy = details.get('strategy') or 'N/A'
        amount = details.get('amount')
        if amount is not None:
            return f"{base}: {symbol} via {strategy} ({amount})"
        return f"{base}: {symbol} via {strategy}"

    def send(self, alert_type: str, details: Optional[Dict[str, Any]] = None, channels: Optional[List[str]] = None) -> Dict[str, Any]:
        if channels is None:
            channels = self._resolve_default_channels()
        else:
            channels = self._filter_channels(channels)

        message = self.build_message(alert_type, details)
        result = {'alert_type': alert_type, 'message': message, 'channels': channels, 'sent': []}
        if self.user:
            notification = Notification.objects.create(
                user=self.user,
                alert_type=alert_type,
                message=message,
                channels=list(channels),
                delivered_channels=[],
                status='queued',
            )
        else:
            notification = None

        for channel in channels:
            try:
                if channel == 'email':
                    self._send_email(message, self.user.email if self.user else None)
                elif channel == 'telegram':
                    self._send_telegram(message)
                elif channel == 'push':
                    self._send_push(message)
                if channel in ('email', 'telegram', 'push'):
                    result['sent'].append(channel)
                    if notification is not None:
                        notification.delivered_channels = list(set(notification.delivered_channels + [channel]))
                        notification.status = 'sent'
                        notification.save(update_fields=['delivered_channels', 'status'])
            except Exception as exc:
                logger.warning('Notification failed for %s: %s', channel, exc)

        if notification is not None and not result['sent']:
            notification.status = 'failed'
            notification.save(update_fields=['status'])

        return result

    def _get_profile(self) -> Optional[Any]:
        if not self.user:
            return None
        profile = getattr(self.user, 'trading_profile', None)
        if profile is not None:
            return profile
        return getattr(self.user, 'bot_settings', None)

    def _resolve_profile_value(self, name: str, default: Any = None) -> Any:
        if not self.user:
            return default
        for source in (getattr(self.user, 'trading_profile', None), getattr(self.user, 'bot_settings', None)):
            if source is not None:
                value = getattr(source, name, None)
                if value not in (None, ''):
                    return value
        return default

    def _resolve_default_channels(self) -> List[str]:
        return self._filter_channels(list(self.CHANNELS))

    def _filter_channels(self, channels: List[str]) -> List[str]:
        profile = self._get_profile()
        if profile is None:
            return channels

        filtered = []
        for channel in channels:
            if channel == 'email' and not getattr(profile, 'email_notifications_enabled', True):
                continue
            if channel == 'telegram' and not getattr(profile, 'telegram_notifications_enabled', False):
                continue
            filtered.append(channel)
        if not filtered and 'push' in channels:
            return ['push']
        return filtered

    def _send_email(self, message: str, recipient: Optional[str]) -> None:
        if not recipient:
            logger.info('Email notification skipped; no recipient configured')
            return

        profile = self._get_profile()
        if profile is not None and not getattr(profile, 'email_notifications_enabled', True):
            logger.info('Email notifications disabled for user %s', self.user.username)
            return

        api_key = self._resolve_profile_value('brevo_api_key') or getattr(settings, 'BREVO_API_KEY', None)
        sender = self._resolve_profile_value('brevo_sender_email') or getattr(settings, 'BREVO_SENDER_EMAIL', None) or recipient

        if not api_key:
            logger.info('Brevo email skipped; API key not configured for %s', recipient)
            return

        url = 'https://api.brevo.com/v3/smtp/email'
        payload = {
            'sender': {'email': sender},
            'to': [{'email': recipient}],
            'subject': 'Deriv Platform Notification',
            'htmlContent': f"<p>{message}</p>",
            'textContent': message,
        }
        data = json.dumps(payload).encode('utf-8')
        req = Request(url, data=data, method='POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('api-key', api_key)
        with urlopen(req, timeout=10) as resp:
            resp.read()

    def _send_telegram(self, message: str) -> None:
        token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
        if not token:
            logger.info('Telegram notification skipped; bot token not configured')
            return

        profile = self._get_profile()
        if profile is not None and not getattr(profile, 'telegram_notifications_enabled', False):
            logger.info('Telegram notifications disabled for user %s', self.user.username)
            return

        chat_id = self._resolve_profile_value('telegram_chat_id') or getattr(settings, 'TELEGRAM_CHAT_ID', None)
        if not chat_id:
            logger.info('Telegram notification skipped; chat_id not configured')
            return

        payload = urlencode({'chat_id': chat_id, 'text': message}).encode('utf-8')
        request = Request(
            f'https://api.telegram.org/bot{token}/sendMessage',
            data=payload,
            method='POST',
        )
        with urlopen(request, timeout=5) as response:
            response.read()

    def _send_push(self, message: str) -> None:
        logger.info('Push notification: %s', message)

    def notify_trade_opened(self, trade, channels: Optional[List[str]] = None) -> Dict[str, Any]:
        details = {
            'symbol': getattr(trade, 'symbol', None),
            'strategy': getattr(trade, 'strategy', None),
            'amount': getattr(trade, 'stake', None),
        }
        return self.send('trade_opened', details=details, channels=channels)

    def notify_trade_closed(self, trade, channels: Optional[List[str]] = None) -> Dict[str, Any]:
        details = {
            'symbol': getattr(trade, 'symbol', None),
            'strategy': getattr(trade, 'strategy', None),
            'amount': getattr(trade, 'profit', None),
        }
        return self.send('trade_closed', details=details, channels=channels)

    def notify_profit_target(self, trade, channels: Optional[List[str]] = None) -> Dict[str, Any]:
        details = {
            'symbol': getattr(trade, 'symbol', None),
            'strategy': getattr(trade, 'strategy', None),
            'amount': getattr(trade, 'profit', None),
        }
        return self.send('profit_target', details=details, channels=channels)

    def notify_drawdown_warning(self, trade, channels: Optional[List[str]] = None) -> Dict[str, Any]:
        details = {
            'symbol': getattr(trade, 'symbol', None),
            'strategy': getattr(trade, 'strategy', None),
            'amount': getattr(trade, 'profit', None),
        }
        return self.send('drawdown_warning', details=details, channels=channels)
