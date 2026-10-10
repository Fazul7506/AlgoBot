import importlib
import sys
from unittest.mock import patch

from django.test import SimpleTestCase


class CeleryImportFallbackTests(SimpleTestCase):
    def _import_with_celery_failure(self, module_name):
        sys.modules.pop(module_name, None)
        original_import = __import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "deriv_platform.celery":
                raise ImportError("simulated celery import failure")
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=guarded_import):
            return importlib.import_module(module_name)

    def test_monitoring_tasks_log_when_celery_import_fails(self):
        with self.assertLogs("apps.monitoring.tasks", level="WARNING") as captured:
            module = self._import_with_celery_failure("apps.monitoring.tasks")

        self.assertIsNone(module.app)
        self.assertTrue(any("Celery app import failed" in entry for entry in captured.output))

    def test_strategy_tasks_log_when_celery_import_fails(self):
        with self.assertLogs("apps.strategies.tasks", level="WARNING") as captured:
            module = self._import_with_celery_failure("apps.strategies.tasks")

        self.assertIsNone(module.app)
        self.assertTrue(any("Celery app import failed" in entry for entry in captured.output))
