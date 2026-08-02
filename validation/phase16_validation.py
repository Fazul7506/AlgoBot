#!/usr/bin/env python
"""
Phase 16 Enterprise Validation Script

Validates production-grade infrastructure scaffolding for Redis, Celery, PostgreSQL, Sentry,
2FA, encrypted credentials, and audit logging.
"""

import os
import sys
from pathlib import Path
import django

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'deriv_platform.settings')
django.setup()

from django.conf import settings


def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


class Phase16Validator:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def test(self, name, func):
        try:
            result = func()
            if result:
                print(f"[PASS] {name}")
                self.passed += 1
            else:
                print(f"[FAIL] {name}")
                self.failed += 1
                self.errors.append(name)
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            self.failed += 1
            self.errors.append(f"{name}: {e}")

    def validate_settings(self):
        def check():
            required = [
                'REDIS_URL', 'CELERY_BROKER_URL', 'CELERY_RESULT_BACKEND',
                'SENTRY_DSN', 'CREDENTIALS_ENCRYPTION_KEY', 'AUDIT_LOG_ENABLED',
                'TWO_FACTOR_ENABLED', 'USE_CELERY', 'USE_POSTGRES'
            ]
            missing = [name for name in required if not hasattr(settings, name)]
            if missing:
                for name in missing:
                    print(f'  - missing setting: {name}')
                return False
            return True

        print_section('Settings')
        self.test('Enterprise settings present', check)

    def validate_models(self):
        def check():
            from core.models import AuditLog, EncryptedCredential
            return hasattr(AuditLog, '__name__') and hasattr(EncryptedCredential, '__name__')

        print_section('Models')
        self.test('AuditLog and EncryptedCredential models exist', check)

    def validate_middleware(self):
        def check():
            return 'core.middleware.audit_middleware.AuditMiddleware' in settings.MIDDLEWARE

        print_section('Middleware')
        self.test('Audit middleware registered', check)

    def validate_celery(self):
        def check():
            try:
                import celery
                from deriv_platform import celery as celery_app
                return hasattr(celery_app, 'app')
            except Exception:
                return False

        print_section('Celery')
        self.test('Celery app present and importable', check)

    def validate_encryption_service(self):
        def check():
            from core.services.encryption_service import CredentialEncryptionService
            service = CredentialEncryptionService(key='test-key')
            encrypted = service.encrypt('secret')
            decrypted = service.decrypt(encrypted)
            return decrypted and 'secret' in decrypted

        print_section('Encryption')
        self.test('CredentialEncryptionService can encrypt and decrypt', check)

    def validate_two_factor(self):
        def check():
            from core.services.two_factor_service import TwoFactorService
            try:
                TwoFactorService.generate_secret()
                return True
            except Exception:
                return False

        print_section('Two-factor auth')
        self.test('Two-factor service can generate secrets', check)

    def validate_sentry(self):
        def check():
            return hasattr(settings, 'SENTRY_DSN')

        print_section('Sentry')
        self.test('Sentry DSN setting exists', check)

    def run_all(self):
        self.validate_settings()
        self.validate_models()
        self.validate_middleware()
        self.validate_celery()
        self.validate_encryption_service()
        self.validate_two_factor()
        self.validate_sentry()

        print_section('Phase 16 Summary')
        print(f'Passed: {self.passed}')
        print(f'Failed: {self.failed}')
        if self.errors:
            print('Errors:')
            for error in self.errors:
                print(f'  - {error}')

        return self.failed == 0


if __name__ == '__main__':
    validator = Phase16Validator()
    success = validator.run_all()
    sys.exit(0 if success else 1)
