from django.test import SimpleTestCase

from apps.brokers.integration_validation import validate_broker_draft


SAFE_ADAPTER = """from apps.brokers.adapters.base import BrokerAdapter

class ExampleAdapter(BrokerAdapter):
    async def connect(self): ...
"""
SAFE_TEST = "def test_adapter_contract():\n    assert True\n"


class BrokerDraftValidationTests(SimpleTestCase):
    def test_valid_adapter_source_passes_preflight(self):
        report = validate_broker_draft([
            {"path": "adapter.py", "content": SAFE_ADAPTER},
            {"path": "test_adapter_contract.py", "content": SAFE_TEST},
            {"path": "README.md", "content": "Review authentication and sandbox setup."},
        ])
        self.assertTrue(report["passed"])
        self.assertEqual(report["errors"], [])

    def test_accepts_adapter_relative_base_import(self):
        source = """from .base import BrokerAdapter

class ExampleAdapter(BrokerAdapter):
    async def connect(self): ...
"""
        report = validate_broker_draft([{"path": "adapter.py", "content": source}])
        self.assertTrue(report["passed"])

    def test_rejects_path_traversal(self):
        report = validate_broker_draft([
            {"path": "../settings.py", "content": "DEBUG = True"},
        ])
        self.assertFalse(report["passed"])
        self.assertTrue(any("Disallowed generated path" in error for error in report["errors"]))

    def test_rejects_syntax_errors(self):
        report = validate_broker_draft([
            {"path": "adapter.py", "content": "class broken(:\n"},
        ])
        self.assertFalse(report["passed"])
        self.assertTrue(any("syntax error" in error for error in report["errors"]))

    def test_requires_base_adapter_import_and_subclass(self):
        report = validate_broker_draft([
            {"path": "adapter.py", "content": "class ExampleAdapter:\n    pass\n"},
        ])
        self.assertFalse(report["passed"])
        self.assertTrue(any("must import BrokerAdapter" in error for error in report["errors"]))
        self.assertTrue(any("inheriting BrokerAdapter" in error for error in report["errors"]))

    def test_rejects_dynamic_execution(self):
        report = validate_broker_draft([
            {"path": "adapter.py", "content": SAFE_ADAPTER + "\neval('1 + 1')\n"},
        ])
        self.assertFalse(report["passed"])
        self.assertTrue(any("dynamic execution" in error for error in report["errors"]))

    def test_rejects_high_risk_import(self):
        report = validate_broker_draft([
            {"path": "adapter.py", "content": SAFE_ADAPTER + "\nimport subprocess\n"},
        ])
        self.assertFalse(report["passed"])
        self.assertTrue(any("high-risk import" in error for error in report["errors"]))

    def test_flags_hard_coded_api_key(self):
        report = validate_broker_draft([
            {"path": "adapter.py", "content": SAFE_ADAPTER + "\napi_key = 'abcdefghijklmnop123456'\n"},
        ])
        self.assertFalse(report["passed"])
        self.assertTrue(any("credential" in error for error in report["errors"]))

    def test_rejects_oversized_files(self):
        report = validate_broker_draft([
            {"path": "adapter.py", "content": "x" * 100_001},
        ])
        self.assertFalse(report["passed"])
        self.assertTrue(any("character limit" in error for error in report["errors"]))
