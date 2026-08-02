import logging
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

try:
    from celery import shared_task
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False


def _send_email(subject, message, from_email, recipient_list):
    send_mail(subject, message, from_email, recipient_list, fail_silently=False)


def send_email(subject, message, recipient_list, from_email=None):
    from_email = from_email or settings.DEFAULT_FROM_EMAIL
    if CELERY_AVAILABLE and getattr(settings, 'USE_CELERY', False):
        try:
            send_email_task.delay(subject, message, from_email, recipient_list)
            return True
        except Exception:
            logger.exception('Failed to queue email task; falling back to synchronous send')
    try:
        _send_email(subject, message, from_email, recipient_list)
        return True
    except Exception:
        logger.exception('Synchronized email send failed')
        return False


if CELERY_AVAILABLE:
    @shared_task(bind=True)
    def send_email_task(self, subject, message, from_email, recipient_list):
        try:
            _send_email(subject, message, from_email, recipient_list)
            return True
        except Exception:
            logger.exception('send_email_task failed')
            return False
else:
    def send_email_task(subject, message, from_email, recipient_list):
        return _send_email(subject, message, from_email, recipient_list)
