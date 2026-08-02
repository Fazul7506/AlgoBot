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
        if self._fernet:
            try:
                return self._fernet.encrypt(text.encode('utf-8')).decode('utf-8')
            except Exception as exc:
                logger.warning('Fernet encryption failed: %s', exc)
        return base64.urlsafe_b64encode(text.encode('utf-8')).decode('utf-8')

    def decrypt(self, token):
        if not token:
            return ''
        if self._fernet:
            try:
                return self._fernet.decrypt(token.encode('utf-8')).decode('utf-8')
            except InvalidToken:
                logger.warning('Encrypted payload could not be decrypted with provided key')
            except Exception as exc:
                logger.warning('Fernet decryption failed: %s', exc)
        try:
            return base64.urlsafe_b64decode(token.encode('utf-8')).decode('utf-8')
        except Exception as exc:
            logger.warning('Base64 fallback decryption failed: %s', exc)
            return token
