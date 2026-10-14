import base64
import hashlib
import json
import logging
from typing import Optional
from django.conf import settings

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    Fernet = None
    InvalidToken = Exception


class CredentialEncryptionService:
    """Encrypt and decrypt credential payloads using Fernet when available."""

    def __init__(self, key: Optional[str] = None):
        self.key = key or getattr(settings, 'CREDENTIALS_ENCRYPTION_KEY', None)
        self._fernet = self._create_fernet()

    def _create_fernet(self):
        if not self.key or not Fernet:
            return None
        raw_key = self.key.encode('utf-8')
        if len(raw_key) == 44 and raw_key.endswith(b'='):
            token = raw_key
        else:
            token = base64.urlsafe_b64encode(hashlib.sha256(raw_key).digest())
        try:
            return Fernet(token)
        except Exception as exc:
            logger.warning('Invalid encryption key for Fernet: %s', exc)
            return None

    def encrypt(self, payload):
        if payload is None:
            return ''
        text = payload if isinstance(payload, str) else json.dumps(payload, separators=(',', ':'))
        if not self._fernet:
            # Base64 is reversible encoding, not encryption. Never persist new
            # broker credentials in plaintext when key material is missing.
            raise RuntimeError(
                "CREDENTIALS_ENCRYPTION_KEY must be configured before storing credentials."
            )
        try:
            return self._fernet.encrypt(text.encode('utf-8')).decode('utf-8')
        except Exception as exc:
            logger.error("broker_credential_encryption_failed", extra={"error_type": exc.__class__.__name__})
            raise RuntimeError("Broker credentials could not be encrypted.") from exc

    def decrypt(self, token):
        if not token:
            return ''
        if not self._fernet:
            raise RuntimeError(
                "CREDENTIALS_ENCRYPTION_KEY is required to read stored broker credentials."
            )
        try:
            return self._fernet.decrypt(token.encode('utf-8')).decode('utf-8')
        except InvalidToken as exc:
            logger.error("broker_credential_decryption_failed")
            if str(token).startswith("gAAAA"):
                raise RuntimeError(
                    "Stored broker credentials cannot be decrypted with the configured key."
                ) from exc
            raise RuntimeError(
                "Legacy broker credentials must be re-encrypted before they can be used."
            ) from exc
        except Exception as exc:
            logger.error("broker_credential_decryption_failed", extra={"error_type": exc.__class__.__name__})
            raise RuntimeError("Stored broker credentials could not be decrypted.") from exc
