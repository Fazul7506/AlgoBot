"""Audit middleware plus the centralized Django-message bridge for API outcomes."""
import json
import logging
from django.utils.deprecation import MiddlewareMixin
from django.contrib import messages
from django.db import connection
from core.models import AuditLog

audit_logger = logging.getLogger('audit')


class AuditMiddleware(MiddlewareMixin):
    """Log requests and turn browser-facing API outcomes into Django messages."""

    EXCLUDED_PATHS = ['/static/', '/media/', '/health/', '/favicon.ico']

    def should_audit(self, request):
        return not any(request.path.startswith(path) for path in self.EXCLUDED_PATHS)

    def process_response(self, request, response):
        if not self.should_audit(request):
            return response
        try:
            self._bridge_message(request, response)
            if not connection.connection or not connection.is_usable():
                return response
            user = getattr(request, 'user', None)
            if user and user.is_authenticated:
                try:
                    AuditLog.objects.create(
                        user=user,
                        path=request.path,
                        method=request.method,
                        status_code=response.status_code,
                        ip_address=self._get_client_ip(request),
                        user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
                        error='',
                    )
                except Exception as e:
                    audit_logger.warning(f"Failed to create audit log: {e}")
        except Exception as e:
            audit_logger.error(f"AuditMiddleware error: {e}")
        return response

    @staticmethod
    def _bridge_message(request, response):
        """Use Django's message framework; never render an API JSON body as UI text."""
        if getattr(response, 'streaming', False):
            return
        path = request.path
        if not (path.startswith('/api/') or path.startswith('/data/')):
            return
        if 'application/json' not in str(response.headers.get('Content-Type', '')).lower():
            return
        try:
            payload = json.loads(response.content.decode('utf-8'))
        except (ValueError, UnicodeDecodeError, AttributeError):
            return
        if not isinstance(payload, dict):
            return
        text = payload.get('message') or payload.get('detail') or payload.get('error')
        if isinstance(text, dict):
            text = text.get('message') or text.get('detail')
        if not isinstance(text, str):
            return
        text = ' '.join(text.split()).strip()[:500]
        if not text or text.startswith('{') or text.startswith('['):
            return
        status = int(getattr(response, 'status_code', 200))
        if status >= 500:
            level = messages.ERROR
        elif status >= 400:
            level = messages.WARNING
        elif payload.get('success') is True or payload.get('status') in {'success', 'ok', 'created', 'updated'}:
            level = messages.SUCCESS
        else:
            level = messages.INFO
        messages.add_message(request, level, text, extra_tags='django-api-message')

    @staticmethod
    def _get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return request.META.get('REMOTE_ADDR')
