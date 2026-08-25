"""Environment-selectable Django settings entrypoint.

Set ``DJANGO_ENV=production`` for deployments.  Render services also select
production settings when that variable is omitted, so a missing dashboard
environment variable cannot silently boot the development configuration.
Development remains the default outside Render.
"""
import os


def deployment_environment(environ=None):
    """Return the effective settings environment for a process environment."""
    environ = os.environ if environ is None else environ
    configured = environ.get("DJANGO_ENV", "").strip().lower()
    if configured:
        return configured
    if environ.get("RENDER", "").strip().lower() == "true":
        return "production"
    return "development"


if deployment_environment() == "production":
    from config.settings.production import *  # noqa: F403,F401
else:
    from config.settings.development import *  # noqa: F403,F401
