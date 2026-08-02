import logging
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone

from core.models import AuditLog

logger = logging.getLogger(__name__)


class AuditMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.audit_start_time = timezone.now()
        request.audit_meta = {
            'path': request.path,
            'method': request.method,
            'query_params': request.GET.dict(),
            'ip_address': request.META.get('REMOTE_ADDR', ''),
            'body': '',
        }

        if request.method in ('POST', 'PUT', 'PATCH'):
            try:
                request.audit_meta['body'] = request.body.decode('utf-8')[:1024]
            except Exception:
                request.audit_meta['body'] = ''

    def process_response(self, request, response):
        if getattr(settings, 'AUDIT_LOG_ENABLED', False):
            try:
                meta = getattr(request, 'audit_meta', {})
                AuditLog.objects.create(
                    user=getattr(request, 'user', None) if getattr(request, 'user', None) and request.user.is_authenticated else None,
                    path=meta.get('path', ''),
                    method=meta.get('method', ''),
                    status_code=response.status_code,
                    ip_address=meta.get('ip_address', ''),
                    query_params=meta.get('query_params', {}),
                    request_body=meta.get('body', ''),
                    response_body=self._truncate_text(getattr(response, 'content', b'').decode('utf-8', errors='ignore'), 1024),
                    error='',
                )
            except Exception:
                logger.exception('AuditMiddleware failed to persist audit log')
        return response

    def process_exception(self, request, exception):
        if getattr(settings, 'AUDIT_LOG_ENABLED', False):
            try:
                meta = getattr(request, 'audit_meta', {})
                AuditLog.objects.create(
                    user=getattr(request, 'user', None) if getattr(request, 'user', None) and request.user.is_authenticated else None,
                    path=meta.get('path', ''),
                    method=meta.get('method', ''),
                    status_code=getattr(exception, 'status_code', 500),
                    ip_address=meta.get('ip_address', ''),
                    query_params=meta.get('query_params', {}),
                    request_body=meta.get('body', ''),
                    response_body='',
                    error=str(exception),
                )
            except Exception:
                logger.exception('AuditMiddleware failed to persist exception audit log')
        return None

    @staticmethod
    def _truncate_text(value, max_length):
        if not value:
            return ''
        if len(value) <= max_length:
            return value
        return value[:max_length] + '...'
