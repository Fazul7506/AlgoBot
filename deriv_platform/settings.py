"""Environment-selectable Django settings entrypoint.

Set DJANGO_ENV=production for Phase 20 deployments. Development remains the
default so existing local workflows are not broken.
"""
import os

if os.getenv("DJANGO_ENV", "development").strip().lower() == "production":
    from config.settings.production import *  # noqa: F403,F401
else:
    from config.settings.development import *  # noqa: F403,F401
