import asyncio
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
from pathlib import Path
from datetime import timedelta

ROOT = Path(__file__).resolve().parents[2]

from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase
from django.utils import timezone
from rest_framework.test import APITestCase, APIRequestFactory, force_authenticate

from apps.brokers.exceptions import BrokerConnectionError, BrokerOrderError
from apps.brokers.models import Broker, BrokerAccount, BrokerConnection, Position
from apps.brokers.position_sync import PositionSyncError
from apps.execution.deriv_views import DerivTradingActionView
from apps.execution.exceptions import OrderValidationError
from apps.execution.models import ExecutionQueue, Order
from apps.execution.signal_validation import SignalValidationService
from apps.execution.tasks import _execution_queue_singleton, process_execution_queue
from .serializers import OrderSerializer
from .views import OrderViewSet, PositionViewSet
from .engine import ExecutionEngine


class OrderSerializerRegressionTests(APITestCase):
    def test_environment_uses_the_model_canonical_account_type(self):
        account = SimpleNamespace(
            account_type='real',
            credentials={'realtime': {'account_type': 'demo'}},
        )
        self.assertEqual(OrderViewSet._environment(account), 'real')

    def test_idempotent_replay_requires_matching_broker_account(self):
        user = get_user_model().objects.create_user(username='idempotency-account', password='test-password')
        broker = Broker.objects.create(name='Deriv', broker_type='deriv', status='active')
        account = BrokerAccount.objects.create(
            user=user, broker=broker, account_id='IDEMPOTENCY-ACCOUNT', status='active'
        )
        Order.objects.create(
            user=user, broker_account=account, symbol='R_100', direction='buy',
            order_type='market', stake='1', client_request_id='same-client-id',
        )
        request = APIRequestFactory().post(
            '/api/orders/', {'client_request_id': 'same-client-id'}, format='json'
        )
        force_authenticate(request, user=user)
        result = OrderViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data['code'], 'CLIENT_REQUEST_ACCOUNT_REQUIRED')

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


class BrokerAuthoritativePositionTests(APITestCase):
    def _account(self, username):
        user = get_user_model().objects.create_user(username=username, password='test-password')
        broker = Broker.objects.create(name='Deriv', broker_type='deriv', status='active')
        account = BrokerAccount.objects.create(
            user=user,
            broker=broker,
            account_id=f'CR-{username}',
            currency='USD',
            status='active',
        )
        BrokerConnection.objects.create(broker=broker, broker_account=account, status='connected')
        return user, account

    def test_open_positions_are_read_from_selected_broker_not_local_position_model(self):
        user, account = self._account('broker-position-test')
        Position.objects.create(
            broker=account.broker,
            account=account,
            contract_id='12345',
            transaction_id='TX-12345',
            symbol='R_100',
            contract_type='CALL',
            stake='100.25',
            entry_price='100.25',
            current_price='101.10',
            profit='0.85',
            currency='USD',
            status='open',
        )
        request = APIRequestFactory().get('/api/positions/open/')
        force_authenticate(request, user=user)

        with patch('apps.execution.views.get_active_account', return_value=account), \
             patch('apps.execution.views.BrokerPositionSyncService') as sync:
            sync.return_value.synchronize = AsyncMock(return_value={
                'meta': {
                    'account_id': account.pk,
                    'broker_account_id': account.account_id,
                }
            })
            result = PositionViewSet.as_view({'get': 'open'})(request)

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['source'], 'broker')
        self.assertEqual(result.data['data'][0]['contract_id'], '12345')
        self.assertEqual(result.data['data'][0]['symbol'], 'R_100')
        self.assertEqual(result.data['data'][0]['profit'], '0.85000000')
        sync.return_value.synchronize.assert_awaited_once_with(account)

    def test_open_positions_return_structured_503_for_unexpected_sync_exception(self):
        user, account = self._account('broker-position-internal-error-test')
        request = APIRequestFactory().get('/api/positions/open/')
        force_authenticate(request, user=user)

        with (
            patch('apps.execution.views.get_active_account', return_value=account),
            patch('apps.execution.views.BrokerPositionSyncService') as sync,
        ):
            sync.return_value.synchronize = AsyncMock(side_effect=RuntimeError('unexpected sync failure'))
            result = PositionViewSet.as_view({'get': 'open'})(request)

        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.data['code'], 'BROKER_POSITION_SYNC_INTERNAL_ERROR')
        self.assertEqual(result.data['status'], 'unavailable')
        self.assertEqual(result.data['data'], [])

    def test_open_positions_return_unavailable_when_broker_state_cannot_be_read(self):
        user, account = self._account('broker-position-error-test')
        request = APIRequestFactory().get('/api/positions/open/')
        force_authenticate(request, user=user)

        with patch('apps.execution.views.get_active_account', return_value=account), \
             patch('apps.execution.views.BrokerPositionSyncService') as sync:
            sync.return_value.synchronize = AsyncMock(
                side_effect=PositionSyncError(
                    'broker unavailable',
                    code='BROKER_UNAVAILABLE',
                )
            )
            result = PositionViewSet.as_view({'get': 'open'})(request)

        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.data['code'], 'BROKER_POSITION_SYNC_FAILED')
        self.assertEqual(result.data['status'], 'unavailable')
        sync.return_value.synchronize.assert_awaited_once_with(account)


class ExecutionQueueTaskTests(TestCase):
    def test_celery_task_name_matches_beat_schedule(self):
        self.assertEqual(process_execution_queue.name, 'apps.execution.process_execution_queue')

    def test_execution_queue_beat_tick_expires_stale_polling_tasks(self):
        from deriv_platform.celery import app

        entry = app.conf.beat_schedule["execution-queue-every-2-seconds"]
        self.assertEqual(entry["task"], "apps.execution.process_execution_queue")
        self.assertEqual(entry["schedule"], 2.0)
        self.assertEqual(entry["options"]["queue"], "celery")
        self.assertEqual(entry["options"]["expires"], 3)

    @patch('apps.execution.tasks.get_redis_connection')
    def test_execution_queue_skips_when_singleton_lock_is_held(self, get_redis_connection):
        lock = get_redis_connection.return_value.lock.return_value
        lock.acquire.return_value = False
        wrapped = _execution_queue_singleton(lambda: {'processed': 1})
        self.assertEqual(wrapped(), {'processed': 0, 'succeeded': 0, 'failed': 0, 'uncertain': 0})
        lock.release.assert_not_called()

    @patch('apps.execution.tasks.get_redis_connection')
    def test_execution_queue_releases_singleton_lock_after_processing(self, get_redis_connection):
        lock = get_redis_connection.return_value.lock.return_value
        lock.acquire.return_value = True
        wrapped = _execution_queue_singleton(lambda: {'processed': 1})
        self.assertEqual(wrapped(), {'processed': 1})
        lock.release.assert_called_once_with()

    @patch('apps.execution.tasks.get_redis_connection')
    def test_queued_order_is_claimed_and_completed(self, get_redis_connection):
        # The production task is protected by a distributed singleton. This
        # regression test must explicitly model successful lock acquisition so
        # it exercises queue claiming/execution rather than depending on CI's
        # Redis availability or an unrelated existing lock.
        lock = get_redis_connection.return_value.lock.return_value
        lock.acquire.return_value = True
        user = get_user_model().objects.create_user(username='queue-regression', password='test-password')
        broker = Broker.objects.create(name='Queue Broker', broker_type='deriv', status='active', supports_live=False)
        account = BrokerAccount.objects.create(user=user, broker=broker, account_id='QUEUE', status='active', credentials={'account_type': 'demo'})
        order = Order.objects.create(user=user, broker_account=account, symbol='R_10', direction='buy', order_type='market', stake='1', status='queued')
        queue = ExecutionQueue.objects.create(
            order=order,
            status='pending',
            next_retry=None,
            queue_type='priority',
        )
        self.assertEqual(
            ExecutionQueue.objects.filter(
                pk=queue.pk,
                status='pending',
                next_retry__isnull=True,
            ).count(),
            1,
        )
        with patch('apps.execution.tasks.ExecutionEngine.execute', new=AsyncMock(return_value=order)) as execute:
            result = process_execution_queue.run.__wrapped__(batch_size=1)
        execute.assert_awaited_once()
        queue.refresh_from_db()
        self.assertEqual(queue.status, 'done')
        self.assertEqual(result['succeeded'], 1)

    @patch('apps.execution.tasks.get_redis_connection')
    def test_unclassified_failure_after_submission_requires_reconciliation(self, get_redis_connection):
        lock = get_redis_connection.return_value.lock.return_value
        lock.acquire.return_value = True
        user = get_user_model().objects.create_user(username='queue-uncertain', password='test-password')
        broker = Broker.objects.create(name='Queue Uncertain Broker', broker_type='deriv', status='active', supports_live=False)
        account = BrokerAccount.objects.create(user=user, broker=broker, account_id='QUEUE-UNCERTAIN', status='active', credentials={'account_type': 'demo'})
        order = Order.objects.create(user=user, broker_account=account, symbol='R_10', direction='buy', order_type='market', stake='1', status='queued')
        queue = ExecutionQueue.objects.create(order=order, status='pending', next_retry=None, queue_type='priority')

        async def post_submit_failure(candidate):
            from asgiref.sync import sync_to_async

            candidate.status = 'sent_to_broker'
            candidate.validation_context = {'execution_mode': 'manual_command'}
            await sync_to_async(Order.objects.filter(pk=candidate.pk).update)(
                status='sent_to_broker',
                validation_context={'execution_mode': 'manual_command'},
            )
            raise RuntimeError('simulated response decode failure')

        with patch('apps.execution.tasks.ExecutionEngine.execute', new=AsyncMock(side_effect=post_submit_failure)):
            result = process_execution_queue.run.__wrapped__(batch_size=1)
        order.refresh_from_db()
        queue.refresh_from_db()
        self.assertEqual(order.status, 'sent_to_broker')
        self.assertTrue(order.validation_context['reconciliation_required'])
        self.assertEqual(queue.status, 'failed')
        self.assertEqual(result['uncertain'], 1)
        self.assertEqual(result['failed'], 0)


class TerminalExecutionContractTests(SimpleTestCase):
    def test_terminal_contract_metadata_is_persisted_in_serializer_contract(self):
        fields = OrderSerializer().fields
        self.assertIn('contract_type', fields)
        self.assertIn('duration', fields)
        self.assertIn('duration_unit', fields)

    def test_client_routing_context_cannot_override_account_currency_or_environment(self):
        account = SimpleNamespace(
            id=7,
            currency='EUR',
            account_type='real',
            credentials={'account_type':'demo'},
        )
        context = OrderViewSet._safe_client_context(
            {
                'symbol':'R_100',
                'contract_type':'CALL',
                'routing_context':{
                    'currency':'USD',
                    'account_type':'demo',
                    'broker_source':'attacker-controlled',
                    'underlying_symbol':'OTHER',
                },
            },
            account,
        )
        self.assertEqual(context['currency'], 'EUR')
        self.assertEqual(context['account_type'], 'real')
        self.assertEqual(context['underlying_symbol'], 'R_100')
        self.assertEqual(context['broker_source'], 'connected_broker')

    def test_unknown_broker_status_is_not_classified_as_execution_success(self):
        source = (ROOT / 'apps' / 'execution' / 'engine.py').read_text()
        self.assertNotIn("or (not broker_status and order.broker_reference)", source)
        self.assertIn('"ExecutionStateUnknown"', source)
        self.assertIn('reconciliation is required', source)

    def test_shared_broker_ui_does_not_bind_terminal_account_selector(self):
        source = (ROOT / 'static' / 'js' / 'live_broker_ui.js').read_text()
        self.assertIn("!document.querySelector('.terminal-page')", source)

    def test_chart_uses_single_live_tick_owner(self):
        chart = (ROOT / 'static' / 'js' / 'deriv_pro_chart.js').read_text()
        self.assertIn("algobot:market-watchdog-tick", chart)
        self.assertNotIn("state.ws=new WebSocket", chart)

    def test_watchdog_does_not_fabricate_bid_ask_from_public_last_tick(self):
        watchdog = (ROOT / 'static' / 'js' / 'terminal_market_watchdog.js').read_text()
        self.assertIn("createTextNode('Unavailable')", watchdog)
        self.assertIn("parsedEpoch > now / 1000 + 5", watchdog)
        self.assertIn("Date.now() - silenceSince > 15000", watchdog)

    def test_terminal_catalogue_and_account_scoped_records_reject_stale_responses(self):
        terminal = (ROOT / 'static' / 'js' / 'trading_terminal.js').read_text()
        self.assertIn("catalogueLoadSeq", terminal)
        self.assertIn("accountId===String(window.AlgoBotAccountContext", terminal)
        self.assertIn("recordsLoadSeq", terminal)
        self.assertIn("signalsLoadSeq", terminal)


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

    def test_direct_deriv_execution_actions_are_disabled(self):
        view = DerivTradingActionView()
        for action in ("buy", "open-contract", "sell", "update", "cancel"):
            request = self.factory.post(f"/api/deriv/{action}/", {}, format="json")
            force_authenticate(request, user=self.user)
            result = view.post(request, action)
            self.assertEqual(result.status_code, 410)
            self.assertEqual(result.data["code"], "NON_CANONICAL_EXECUTION_ENDPOINT")
            self.assertEqual(result.data["canonical_endpoint"], "/api/orders/")

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


class OrderCancellationSafetyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='order-cancel-safety', password='test-password')
        self.broker = Broker.objects.create(name='Deriv', broker_type='deriv', status='active')
        self.account = BrokerAccount.objects.create(
            user=self.user, broker=self.broker, account_id='CANCEL-SAFETY', status='active'
        )

    def _order(self, status):
        return Order.objects.create(
            user=self.user, broker_account=self.account, symbol='R_100',
            direction='buy', order_type='market', stake='1', status=status,
        )

    def test_queued_order_cancellation_atomically_cancels_pending_queue(self):
        order = self._order('queued')
        queue = ExecutionQueue.objects.create(order=order, status='pending')
        cancelled = ExecutionEngine().cancel_order(order)
        queue.refresh_from_db()
        self.assertEqual(cancelled.status, 'cancelled')
        self.assertEqual(queue.status, 'cancelled')

    def test_submitted_order_cannot_be_marked_cancelled_locally(self):
        order = self._order('sent_to_broker')
        with self.assertRaises(OrderValidationError):
            ExecutionEngine().cancel_order(order)
        order.refresh_from_db()
        self.assertEqual(order.status, 'sent_to_broker')

    def test_processing_queue_cannot_be_cancelled_as_if_not_submitted(self):
        order = self._order('queued')
        queue = ExecutionQueue.objects.create(order=order, status='processing')
        with self.assertRaises(OrderValidationError):
            ExecutionEngine().cancel_order(order)
        queue.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(queue.status, 'processing')
        self.assertEqual(order.status, 'queued')

    def test_submitted_order_retry_endpoint_is_forbidden(self):
        order = self._order('sent_to_broker')
        request = APIRequestFactory().post(f'/api/orders/{order.pk}/retry/', {}, format='json')
        force_authenticate(request, user=self.user)
        result = OrderViewSet.as_view({'post': 'retry'})(request, pk=order.pk)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data['code'], 'EXECUTION_RETRY_FORBIDDEN')

    def test_failed_order_retry_is_rejected_while_worker_owns_queue(self):
        order = self._order('failed')
        ExecutionQueue.objects.create(order=order, status='processing')
        request = APIRequestFactory().post(f'/api/orders/{order.pk}/retry/', {}, format='json')
        force_authenticate(request, user=self.user)
        result = OrderViewSet.as_view({'post': 'retry'})(request, pk=order.pk)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data['code'], 'EXECUTION_RETRY_IN_PROGRESS')

    def test_manual_retry_clears_stale_queue_deadline(self):
        order = self._order('failed')
        queue = ExecutionQueue.objects.create(
            order=order, status='failed', next_retry=timezone.now() + timedelta(hours=1)
        )
        request = APIRequestFactory().post(f'/api/orders/{order.pk}/retry/', {}, format='json')
        force_authenticate(request, user=self.user)
        result = OrderViewSet.as_view({'post': 'retry'})(request, pk=order.pk)
        self.assertEqual(result.status_code, 200)
        queue.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(queue.status, 'pending')
        self.assertIsNone(queue.next_retry)
        self.assertEqual(order.status, 'queued')
