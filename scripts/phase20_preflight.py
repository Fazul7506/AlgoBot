"""Phase 20 production preflight.

Run only after .env.production has been populated:
    DJANGO_ENV=production python scripts/phase20_preflight.py
"""
import os
import sys

os.environ.setdefault("DJANGO_ENV", "production")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")

import django
django.setup()

from django.conf import settings
from django.core.management import call_command

print("=== PHASE 20A-F PRODUCTION PREFLIGHT ===")
print("DEBUG:", settings.DEBUG)
print("BASE_URL:", settings.BASE_URL)
print("ALLOWED_HOSTS:", settings.ALLOWED_HOSTS)
print("DATABASE ENGINE:", settings.DATABASES["default"]["ENGINE"])
print("REDIS ENABLED:", getattr(settings, "USE_REDIS", False))

call_command("check", deploy=True)
call_command("makemigrations", "--check", verbosity=1)
print("PREFLIGHT: PASS")
