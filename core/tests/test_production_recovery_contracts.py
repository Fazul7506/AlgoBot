from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]


class ProductionRecoveryContractTests(SimpleTestCase):
    def test_redis_pools_are_explicitly_bounded(self):
        cache = (ROOT / "config" / "settings" / "cache.py").read_text(encoding="utf-8")
        celery = (ROOT / "config" / "settings" / "celery.py").read_text(encoding="utf-8")
        self.assertIn('"max_connections": REDIS_CACHE_MAX_CONNECTIONS', cache)
        self.assertIn("REDIS_CACHE_MAX_CONNECTIONS", cache)
        self.assertIn("CELERY_BROKER_POOL_LIMIT", celery)
        self.assertIn('"max_connections": max(1, int(os.environ.get("CELERY_REDIS_MAX_CONNECTIONS", "4")))', celery)

    def test_drf_uses_resilient_throttles(self):
        base = (ROOT / "config" / "settings" / "base.py").read_text(encoding="utf-8")
        throttling = (ROOT / "core" / "throttling.py").read_text(encoding="utf-8")
        self.assertIn("core.throttling.ResilientAnonRateThrottle", base)
        self.assertIn("core.throttling.ResilientUserRateThrottle", base)
        self.assertIn("class ResilientUserRateThrottle", throttling)
        self.assertIn("_fallback_cache", throttling)

    def test_billing_boot_waits_for_deferred_frontend_transport(self):
        billing = (ROOT / "templates" / "core" / "billing.html").read_text(encoding="utf-8")
        self.assertIn("const boot = () => {", billing)
        self.assertIn("document.addEventListener('DOMContentLoaded', boot, {once:true})", billing)
        self.assertIn("window.AlgoBotFrontendData.request", billing)

    def test_live_broker_ui_reads_canonical_selected_account(self):
        live = (ROOT / "static" / "js" / "live_broker_ui.js").read_text(encoding="utf-8")
        self.assertIn("window.AlgoBotAccountContext?.getSelected?.()", live)
        self.assertIn("return accounts.find(a => a.is_active || a.is_default || a.is_preferred)", live)
