from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        import core.signals  # noqa: F401
        
        # Validate OAuth configuration on startup
        import logging
        from core.services.oauth_service import DerivOAuthService
        
        logger = logging.getLogger("oauth")
        is_valid, error_msg = DerivOAuthService.validate_configuration()
        
        if not is_valid:
            logger.warning(f"OAuth Configuration Warning: {error_msg}")
        else:
            logger.info("OAuth configuration validated successfully")
