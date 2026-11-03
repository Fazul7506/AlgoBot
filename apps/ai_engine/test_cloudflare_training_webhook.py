import os
from django.test import RequestFactory, SimpleTestCase
from unittest.mock import patch

from apps.ai_engine.cloudflare_hooks import (
    MAX_TRAINING_WEBHOOK_BODY_BYTES,
    cloudflare_training_dispatch,
)


class CloudflareTrainingWebhookTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch.dict(os.environ, {"CLOUDFLARE_TRAINING_WEBHOOK_TOKEN": "test-secret"})
    def test_oversized_training_payload_is_rejected(self):
        request = self.factory.post(
            "/api/internal/cloudflare/ai-training/",
            data=b"x" * (MAX_TRAINING_WEBHOOK_BODY_BYTES + 1),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-secret",
        )
        response = cloudflare_training_dispatch(request)
        self.assertEqual(response.status_code, 413)
