from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from core.exceptions import custom_exception_handler


class APIErrorContractTests(SimpleTestCase):
    def test_validation_errors_include_plain_language_message_and_stable_code(self):
        request = APIRequestFactory().post("/api/backtests/", {"timeframe": "unsupported"})
        response = custom_exception_handler(
            ValidationError({"timeframe": ["Choose a supported timeframe."]}),
            {"request": request, "view": object()},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error_code"], "invalid")
        self.assertIn("timeframe", response.data["user_message"])
        self.assertIn("supported timeframe", response.data["user_message"])
