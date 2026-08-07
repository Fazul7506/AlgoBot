from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        import core.signals  # noqa: F401
        
        # Validate OAuth configuration on startup (production only)
        from django.conf import settings
        from core.services.oauth_service import DerivOAuthService
        
        if not settings.DEBUG:
            # Only validate in production
            is_valid, error_msg = DerivOAuthService.validate_configuration()
            if not is_valid:
                import logging
                logger = logging.getLogger("oauth")
                logger.error(f"CRITICAL: OAuth Configuration Error: {error_msg}")
