from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.ai_engine.artifact_storage import _hash_file, _signature, schema_document


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

    def test_streaming_file_signature_matches_in_memory_signature(self):
        payload = (b"algobot-model-artifact-" * 100_000) + b"end"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.joblib"
            path.write_bytes(payload)
            self.assertEqual(
                _hash_file(path, "streaming-test-key"),
                _signature(payload, "streaming-test-key"),
            )
