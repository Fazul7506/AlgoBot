import asyncio
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase
from rest_framework.test import APITestCase, APIRequestFactory, force_authenticate

from apps.brokers.exceptions import BrokerConnectionError, BrokerOrderError
from apps.brokers.models import Broker, BrokerAccount
from apps.execution.deriv_views import DerivTradingActionView
from apps.execution.models import ExecutionQueue, Order
from apps.execution.signal_validation import SignalValidationService
from apps.execution.tasks import process_execution_queue
from .serializers import OrderSerializer
from .views import OrderViewSet
from .engine import ExecutionEngine


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

    def test_manual_terminal_order_executes_immediately_without_queue(self):
        user = SimpleNamespace(id=1)
        account = SimpleNamespace(id=7, user_id=1, is_connection_eligible=True)
        order = SimpleNamespace(status='validated', user=user, broker_account_id=7)
        engine = ExecutionEngine()
        with patch.object(engine, '_assert_authoritative_account', return_value=account), \
             patch('apps.execution.engine.OrderService.create_order', return_value=order), \
             patch('apps.execution.engine.OrderValidationService.validate'), \
             patch('apps.risk.engine.RiskEngine.approve_or_raise'), \
             patch.object(engine, 'execute', new=AsyncMock(return_value=order)) as execute, \
             patch('apps.execution.engine.ExecutionQueueService.enqueue') as enqueue:
            result = engine.place_manual_order(
                user,
                broker_account=account,
                symbol='R_100',
                direction='buy',
                order_type='market',
                stake='1',
            )
        self.assertIs(result, order)
        execute.assert_awaited_once_with(order)
        enqueue.assert_not_called()


class ExecutionQueueTaskTests(TestCase):
    def test_celery_task_name_matches_beat_schedule(self):
        self.assertEqual(process_execution_queue.name, 'apps.execution.process_execution_queue')

    def test_queued_order_is_claimed_and_completed(self):
        user = get_user_model().objects.create_user(username='queue-regression', password='test-password')
        broker = Broker.objects.create(name='Queue Broker', broker_type='paper', status='active', supports_live=False)
        account = BrokerAccount.objects.create(user=user, broker=broker, account_id='QUEUE', status='active', credentials={'account_type': 'demo'})
        order = Order.objects.create(user=user, broker_account=account, symbol='R_10', direction='buy', order_type='market', stake='1', status='queued')
        queue = ExecutionQueue.objects.create(order=order, status='pending')
        with patch('apps.execution.tasks.ExecutionEngine.execute', new=AsyncMock(return_value=order)) as execute:
            result = process_execution_queue.run(batch_size=1)
        execute.assert_awaited_once()
        queue.refresh_from_db()
        self.assertEqual(queue.status, 'done')
        self.assertEqual(result['succeeded'], 1)


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
