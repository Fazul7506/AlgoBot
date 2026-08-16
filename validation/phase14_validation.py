#!/usr/bin/env python
"""
Phase 14 SaaS Validation Script

Checks that payment/billing/referral pieces are present and wired:
- required payment provider settings
- payment service methods
- webhook URL registered
- billing models & fields exist
- trade limit enforcement present in TradeService.open_trade
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


class Phase14Validator:
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
            ok = True
            prov = getattr(settings, 'PAYMENT_PROVIDER', None)
            if not prov:
                print('  - PAYMENT_PROVIDER missing')
                ok = False
            supported = {'intasend', 'pesapal'}
            if str(prov).lower() not in supported:
                print(f'  - unsupported payment provider: {prov}')
                ok = False
            for name in (
                'INTASEND_PUBLIC_KEY', 'INTASEND_SECRET_KEY', 'INTASEND_WEBHOOK_CHALLENGE',
                'PESAPAL_CONSUMER_KEY', 'PESAPAL_CONSUMER_SECRET', 'PESAPAL_NOTIFICATION_ID',
            ):
                if not hasattr(settings, name):
                    print(f'  - {name} setting missing')
                    ok = False
            return ok

        print_section('Settings')
        self.test('Payment provider settings present', check)

    def validate_models(self):
        def check():
            from core import models as core_models
            ok = True
            for name in ('Invoice', 'Payment', 'ReferralReward', 'Subscription', 'UserProfile'):
                if not hasattr(core_models, name):
                    print(f'  - core.models missing {name}')
                    ok = False

            # Check subscription fields
            sub = getattr(core_models, 'Subscription', None)
            if sub:
                for field in ('price_cents', 'currency', 'recurring', 'max_concurrent_trades'):
                    if field not in [f.name for f in sub._meta.get_fields()]:
                        print(f'  - Subscription missing field {field}')
                        ok = False

            return ok

        print_section('Models')
        self.test('Billing and subscription models present', check)

    def validate_payment_service(self):
        def check():
            from core.services.payment_service import PaymentService
            svc = PaymentService()
            has_create = hasattr(svc, 'create_checkout_session')
            has_handle = hasattr(svc, 'handle_webhook')
            if not has_create:
                print('  - create_checkout_session missing')
            if not has_handle:
                print('  - handle_webhook missing')
            return has_create and has_handle

        print_section('PaymentService')
        self.test('PaymentService exposes create_checkout_session and handle_webhook', check)

    def validate_urls(self):
        def check():
            from django.urls import get_resolver
            resolver = get_resolver(None)
            patterns = [p.pattern._route if hasattr(p.pattern, '_route') else str(p.pattern) for p in resolver.url_patterns]
            required = ('webhooks/intasend', 'webhooks/pesapal', 'payments/pesapal/callback')
            found = all(any(route in p or route + '/' in p for p in patterns) for route in required)
            if not found:
                print('  - IntaSend/Pesapal webhook or callback URL missing')
            return found

        print_section('URLs')
        self.test('IntaSend and Pesapal webhook URLs registered', check)

    def validate_trade_limits_enforcement(self):
        def check():
            from trading.services.trade_service import TradeService
            import inspect
            src = inspect.getsource(TradeService.open_trade)
            return 'max_concurrent_trades' in src or 'open_trades = Trade.objects.filter' in src

        print_section('Trade limits enforcement')
        self.test('TradeService.open_trade enforces subscription max concurrent trades', check)

    def validate_migrations(self):
        def check():
            # Instead of relying on filenames (which change when migrations are recreated),
            # verify the billing models' database tables exist. This works after migrations
            # were re-run and is resilient to renamed migration files.
            from django.db import connection
            from core import models as core_models

            required = ['Invoice', 'Payment', 'ReferralReward']
            missing_models = []
            tables_to_check = []
            for name in required:
                model = getattr(core_models, name, None)
                if not model:
                    missing_models.append(name)
                else:
                    tables_to_check.append(model._meta.db_table)

            if missing_models:
                for m in missing_models:
                    print(f'  - core.models missing {m}')
                return False

            existing_tables = connection.introspection.table_names()
            missing_tables = [t for t in tables_to_check if t not in existing_tables]
            if missing_tables:
                print(f'  - Missing DB tables for billing models: {missing_tables}')
                return False

            return True

        print_section('Migrations / DB')
        self.test('Core billing DB tables present', check)

    def run_all(self):
        self.validate_settings()
        self.validate_models()
        self.validate_payment_service()
        self.validate_urls()
        self.validate_trade_limits_enforcement()
        self.validate_migrations()

        print_section('Phase 14 Summary')
        print(f'Passed: {self.passed}')
        print(f'Failed: {self.failed}')
        if self.errors:
            print('Errors:')
            for error in self.errors:
                print(f'  - {error}')

        return self.failed == 0


if __name__ == '__main__':
    v = Phase14Validator()
    ok = v.run_all()
    sys.exit(0 if ok else 1)
