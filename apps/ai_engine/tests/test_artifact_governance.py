from __future__ import annotations

import unittest

from apps.ai_engine.artifact_storage import _signature, schema_document


class ModelArtifactGovernanceTests(unittest.TestCase):
    def test_feature_schema_preserves_exact_order_and_dtype(self):
        schema = schema_document(("close_return", "rolling_volatility"))
        self.assertEqual(schema["feature_names"], ["close_return", "rolling_volatility"])
        self.assertEqual(
            [item["position"] for item in schema["features"]],
            [0, 1],
        )
        self.assertEqual(
            [item["dtype"] for item in schema["features"]],
            ["float64", "float64"],
        )

    def test_artifact_signature_is_deterministic_and_keyed(self):
        payload = b"trusted model bytes"
        digest_a, signature_a = _signature(payload, "test-key-a")
        digest_b, signature_b = _signature(payload, "test-key-b")
        self.assertEqual(digest_a, digest_b)
        self.assertNotEqual(signature_a, signature_b)

    def test_artifact_signature_changes_when_payload_changes(self):
        digest_a, signature_a = _signature(b"model-a", "test-key")
        digest_b, signature_b = _signature(b"model-b", "test-key")
        self.assertNotEqual(digest_a, digest_b)
        self.assertNotEqual(signature_a, signature_b)
