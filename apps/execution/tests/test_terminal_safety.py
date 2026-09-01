from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.brokers.exceptions import BrokerConnectionError, BrokerOrderError
from apps.execution.deriv_views import DerivTradingActionView


class DerivTerminalSafetyTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, id=1)
        self.account = SimpleNamespace(
            id=7,
            broker=SimpleNamespace(broker_type="deriv"),
            is_connection_eligible=True,
        )

    def request(self):
        request = self.factory.post("/api/deriv/buy/", {})
        force_authenticate(request, user=self.user)
        return request

    def test_connection_failure_is_unknown_and_non_retryable(self):
        view = DerivTradingActionView()
        with patch.object(view, "_account", return_value=self.account), patch(
            "apps.execution.deriv_views.DerivTradingOperations"
        ) as operations:
            operations.return_value = object()
            response = view._execute(
                self.request(),
                lambda _ops: (_ for _ in ()).throw(BrokerConnectionError("connection lost")),
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["status"], "unknown")
        self.assertEqual(response.data["code"], "BROKER_EXECUTION_STATE_UNKNOWN")
        self.assertFalse(response.data["retryable"])
        self.assertTrue(response.data["reconciliation_required"])

    def test_broker_rejection_is_not_reported_as_unknown(self):
        view = DerivTradingActionView()
        with patch.object(view, "_account", return_value=self.account), patch(
            "apps.execution.deriv_views.DerivTradingOperations"
        ) as operations:
            operations.return_value = object()
            response = view._execute(
                self.request(),
                lambda _ops: (_ for _ in ()).throw(BrokerOrderError("contract rejected")),
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["status"], "rejected")
        self.assertFalse(response.data["retryable"])
