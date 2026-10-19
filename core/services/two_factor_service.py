"""TOTP enrollment, encrypted secret storage and single-use recovery codes."""
import hashlib
import hmac
import logging
import secrets

from django.conf import settings

from core.services.encryption_service import CredentialEncryptionService

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
            raise RuntimeError("pyotp is required for 2FA support")
        return pyotp.random_base32()

    @staticmethod
    def encrypt_secret(secret):
        # Fail closed: never persist a TOTP seed in plaintext.
        return CredentialEncryptionService().encrypt(secret)

    @staticmethod
    def decrypt_secret(encrypted_secret):
        if not encrypted_secret:
            return ""
        return CredentialEncryptionService().decrypt(encrypted_secret)

    def get_totp(self):
        if pyotp is None or not self.secret:
            return None
        return pyotp.TOTP(self.secret)

    def get_uri(self, username, issuer=None):
        if not self.secret or pyotp is None:
            return None
        issuer = issuer or getattr(settings, "TWO_FACTOR_ISSUER", "AlgoBot")
        return self.get_totp().provisioning_uri(name=username, issuer_name=issuer)

    def validate_token(self, token):
        if pyotp is None or not self.secret:
            return False
        try:
            token = str(token or "").replace(" ", "").strip()
            return len(token) == 6 and token.isdigit() and self.get_totp().verify(token, valid_window=1)
        except Exception as exc:
            logger.warning("2FA validation failed: %s", exc.__class__.__name__)
            return False


def generate_recovery_codes(count=10):
    """Return one-time display values and only their SHA-256 digests for storage."""
    codes = [secrets.token_hex(5).upper() for _ in range(count)]
    return codes, [hashlib.sha256(code.encode("ascii")).hexdigest() for code in codes]


def verify_user_code(profile, token, *, consume_recovery=False):
    """Validate a TOTP or a single-use recovery code against a profile."""
    token = str(token or "").strip().replace(" ", "")
    try:
        secret = TwoFactorService.decrypt_secret(profile.two_factor_secret_encrypted)
    except RuntimeError:
        logger.error("2fa_secret_decryption_unavailable")
        return False
    if secret and TwoFactorService(secret).validate_token(token):
        return True
    if not token or not profile.two_factor_recovery_codes:
        return False
    digest = hashlib.sha256(token.upper().encode("utf-8")).hexdigest()
    matches = [
        hmac.compare_digest(str(saved), digest)
        for saved in profile.two_factor_recovery_codes
    ]
    if not any(matches):
        return False
    if consume_recovery:
        profile.two_factor_recovery_codes = [
            saved for saved, matched in zip(profile.two_factor_recovery_codes, matches)
            if not matched
        ]
        profile.save(update_fields=["two_factor_recovery_codes", "updated_at"])
    return True
