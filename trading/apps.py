from django.apps import AppConfig


class TradingConfig(AppConfig):
    """Compatibility Django app for the legacy trading package.

    The canonical trading engine lives in ``apps.trading`` and uses the
    ``engine_trading`` label. The legacy views/models are still imported by
    the URL layer, so this package must also be a registered Django app, but
    with its own label to avoid a registry collision.
    """

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'trading'
    label = 'legacy_trading'
    verbose_name = 'Legacy Trading Compatibility'
