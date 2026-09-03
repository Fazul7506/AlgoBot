from unittest.mock import patch
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase, APIRequestFactory, force_authenticate

from apps.brokers.exceptions import BrokerConnectionError, BrokerOrderError
from apps.execution.deriv_views import DerivTradingActionView
from apps.execution.signal_validation import SignalValidationService
from .serializers import OrderSerializer
from .views import OrderViewSet


class OrderSerializerRegressionTests(APITestCase):
    def test_terminal_order_values_are_normalized(self):
        serializer = OrderSerializer()
        self.assertEqual(serializer.validate_direction('BUY'), 'buy')
        self.assertEqual(serializer.validate_direction('sell'), 'sell')
        self.assertEqual(serializer.validate_order_type('MARKET'), 'market')
        self.assertEqual(serializer.validate_order_type('limit'), 'limit')

    def test_preview_converts_unexpected_internal_failure_to_structured_503(self):
        user = get_user_model().objects.create_user(username='preview-regression', password='test-password')
        request = APIRequestFactory().post('/api/orders/preview/', {'symbol': '1HZ100V', 'direction': 'buy', 'order_type': 'market', 'stake': '1'}, format='json')
        force_authenticate(request, user=user)
        view = OrderViewSet.as_view({'post': 'preview'})
        with patch.object(OrderSerializer, 'is_valid', side_effect=RuntimeError('synthetic preview failure')):
            result = view(request)
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.data['code'], 'PREVIEW_INTERNAL_ERROR')
        self.assertEqual(result.data['status'], 'rejected')


class SignalValidationServiceTests(SimpleTestCase):
    def test_returns_structured_validation_errors(self):
        result = SignalValidationService().validate(
            signal={}, trading_enabled=False, websocket_connected=False
        )
        self.assertFalse(result.is_valid)
        self.assertIn("Trading is disabled", result.errors)
        self.assertIn("Websocket is not connected", result.errors)


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
                lambda _ops: (_ for _ in ()).throw(
                    BrokerConnectionError("connection lost")
                ),
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
                lambda _ops: (_ for _ in ()).throw(
                    BrokerOrderError("contract rejected")
                ),
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["status"], "rejected")
        self.assertFalse(response.data["retryable"])
