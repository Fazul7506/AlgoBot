import logging
from django.conf import settings

try:
    import pyotp
except ImportError:
    pyotp = None

logger = logging.getLogger(__name__)


class TwoFactorService:
    def __init__(self, secret=None):
        self.secret = secret

    @staticmethod
    def generate_secret():
        if pyotp is None:
            raise RuntimeError('pyotp is required for 2FA support')
        return pyotp.random_base32()

    def get_totp(self):
        if pyotp is None or not self.secret:
            return None
        return pyotp.TOTP(self.secret)

    def get_uri(self, username, issuer=None):
        if not self.secret or pyotp is None:
            return None
        issuer = issuer or getattr(settings, 'TWO_FACTOR_ISSUER', 'DerivBot')
        return self.get_totp().provisioning_uri(name=username, issuer_name=issuer)

    def validate_token(self, token):
        if pyotp is None or not self.secret:
            return False
        try:
            return self.get_totp().verify(token, valid_window=1)
        except Exception as exc:
            logger.warning('2FA validation failed: %s', exc)
            return False
