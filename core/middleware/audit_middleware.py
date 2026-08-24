"""Audit middleware for logging all requests and responses."""
import logging
from django.utils.deprecation import MiddlewareMixin
from django.db import connection
from core.models import AuditLog

audit_logger = logging.getLogger('audit')


class AuditMiddleware(MiddlewareMixin):
    """Log all HTTP requests and responses for audit trail."""
    
    EXCLUDED_PATHS = [
        '/static/',
        '/media/',
        '/health/',
        '/favicon.ico',
    ]
    
    def should_audit(self, request):
        """Check if request should be audited."""
        for excluded in self.EXCLUDED_PATHS:
            if request.path.startswith(excluded):
                return False
        return True
    
    def process_response(self, request, response):
        """Log response after it's been created."""
        if not self.should_audit(request):
            return response
        
        try:
            # Skip audit logging if database is locked
            if not connection.connection or connection.connection.closed:
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
                    # Log but don't fail the request if audit logging fails
                    audit_logger.warning(f"Failed to create audit log: {e}")
        except Exception as e:
            audit_logger.error(f"AuditMiddleware error: {e}")
        
        return response
    
    @staticmethod
    def _get_client_ip(request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
