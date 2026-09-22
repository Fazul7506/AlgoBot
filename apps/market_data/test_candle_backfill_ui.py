from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CandleBackfillEvent, CandleBackfillRun, MarketSymbol


class CandleBackfillUiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="backfill-admin",
            password="test-password",
            is_staff=True,
        )
        self.deriv_symbol = MarketSymbol.objects.create(
            symbol="R_100",
            display_name="Volatility 100",
            market="Volatility Indices",
            broker="deriv",
            is_active=True,
            is_tradable=True,
        )
        MarketSymbol.objects.create(
            symbol="OTHER_100",
            display_name="Other Broker 100",
            market="Volatility Indices",
            broker="other",
            is_active=True,
            is_tradable=True,
        )
        self.client.force_login(self.user)

    def test_empty_page_exposes_start_control_and_truthful_criteria(self):
        response = self.client.get(reverse("initial_candle_backfill"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Start backfill")
        self.assertContains(response, "BACKFILL CRITERIA")
        self.assertContains(response, "broker=deriv")
        self.assertContains(response, "Not started")
        self.assertContains(response, "No initial run exists")
        self.assertNotContains(response, "Loading live state")

    def test_json_empty_state_is_explicit_and_contains_config(self):
        response = self.client.get(
            reverse("initial_candle_backfill"),
            {"format": "json", "scope": "initial"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNone(payload["initial"])
        self.assertEqual(payload["config"]["count"], 5000)
        self.assertEqual(payload["config"]["eligible_symbol_count"], 1)
        self.assertIn("1m", payload["config"]["native_timeframes"])

    def test_start_button_creates_dispatchable_run(self):
        published = SimpleNamespace(id="ui-start-task")
        before = timezone.now()
        with patch(
            "apps.market_data.tasks.run_initial_candle_backfill.apply_async",
            return_value=published,
        ) as publish:
            response = self.client.post(
                reverse("initial_candle_backfill"),
                {"symbol": ""},
            )

        self.assertEqual(response.status_code, 302)
        run = CandleBackfillRun.objects.get(scope="initial")
        self.assertEqual(run.status, "running")
        self.assertEqual(run.count, 5000)
        self.assertEqual(run.task_id, "ui-start-task")
        self.assertIsNotNone(run.dispatch_at)
        self.assertGreaterEqual(run.requested_at, before - timedelta(seconds=2))
        self.assertEqual(run.symbol, "")
        self.assertTrue(
            CandleBackfillEvent.objects.filter(
                run=run, event_type="dispatch"
            ).exists()
        )
        publish.assert_called_once_with(
            args=(run.pk,),
            kwargs={"count": 5000, "symbol": None},
            queue="market_data",
        )

    def test_manual_dispatch_uses_the_dedicated_market_data_queue(self):
        published = SimpleNamespace(id="market-data-task")
        with patch(
            "apps.market_data.tasks.run_initial_candle_backfill.apply_async",
            return_value=published,
        ) as publish:
            response = self.client.post(
                reverse("initial_candle_backfill"),
                {"symbol": ""},
            )

        self.assertEqual(response.status_code, 302)
        run = CandleBackfillRun.objects.get(scope="initial")
        self.assertEqual(run.task_id, "market-data-task")
        publish.assert_called_once_with(
            args=(run.pk,),
            kwargs={"count": 5000, "symbol": None},
            queue="market_data",
        )
        self.assertTrue(
            CandleBackfillEvent.objects.filter(
                run=run,
                message__icontains="market-data worker",
            ).exists()
        )

    def test_selected_symbol_must_be_active_tradable_deriv_symbol(self):
        response = self.client.post(
            reverse("initial_candle_backfill"),
            {"symbol": "OTHER_100"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CandleBackfillRun.objects.filter(scope="initial").exists())

    def test_running_run_cannot_be_started_twice(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
        )
        with patch("apps.market_data.tasks.run_initial_candle_backfill.apply_async") as publish:
            response = self.client.post(
                reverse("initial_candle_backfill"),
                {"symbol": ""},
            )
        self.assertEqual(response.status_code, 302)
        run.refresh_from_db()
        self.assertEqual(run.pk, CandleBackfillRun.objects.get(scope="initial").pk)
        publish.assert_not_called()

    def test_failed_run_can_be_retried_with_new_request_timestamp(self):
        old_requested = timezone.now() - timedelta(hours=2)
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="failed",
            count=5000,
            error="Deriv timeout",
        )
        CandleBackfillRun.objects.filter(pk=run.pk).update(requested_at=old_requested)
        published = SimpleNamespace(id="retry-task")
        with patch(
            "apps.market_data.tasks.run_initial_candle_backfill.apply_async",
            return_value=published,
        ):
            response = self.client.post(
                reverse("initial_candle_backfill"),
                {"symbol": "R_100"},
            )
        self.assertEqual(response.status_code, 302)
        run.refresh_from_db()
        self.assertEqual(run.status, "running")
        self.assertEqual(run.symbol, "R_100")
        self.assertEqual(run.task_id, "retry-task")
        self.assertGreater(run.requested_at, old_requested)

    def test_json_payload_exposes_render_aligned_state_and_actual_delivery_queue(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
            task_id="render-task",
            accepted_at=timezone.now(),
            started_at=None,
            result={"trigger": "automatic", "automatic_attempts": 2},
        )
        CandleBackfillEvent.objects.create(
            run=run,
            event_type="worker_received",
            level="info",
            message="received via celery",
            task_id="render-task",
            payload={"queue": "celery"},
        )
        response = self.client.get(
            reverse("initial_candle_backfill"),
            {"format": "json", "scope": "initial"},
        )
        payload = response.json()
        self.assertEqual(payload["initial"]["render_status"], "pending")
        self.assertEqual(payload["initial"]["render_status_label"], "Pending")
        self.assertEqual(payload["initial"]["delivery_queue"], "celery")
        self.assertEqual(payload["initial"]["automatic_attempts"], 2)

    def test_json_log_level_filter_is_supported(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="failed",
            count=5000,
            error="Deriv timeout",
        )
        CandleBackfillEvent.objects.create(run=run, level="info", event_type="dispatch", message="queued")
        error_event = CandleBackfillEvent.objects.create(run=run, level="error", event_type="failed", message="failed")
        response = self.client.get(
            reverse("initial_candle_backfill"),
            {"format": "json", "scope": "initial", "level": "error"},
        )
        events = response.json()["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["id"], error_event.id)
        self.assertEqual(events[0]["level"], "error")

    def test_json_received_state_is_not_reported_as_running(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
            task_id="received-task",
            accepted_at=timezone.now(),
            started_at=None,
        )
        response = self.client.get(
            reverse("initial_candle_backfill"),
            {"format": "json", "scope": "initial"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()["initial"]
        self.assertEqual(payload["worker_state"], "RECEIVED")
        self.assertEqual(payload["status_label"], "Worker received")
        self.assertFalse(payload["live"])
        self.assertEqual(payload["duration_seconds"], 0)
        self.assertIn("received the task", payload["notices"][0]["message"])

    def test_json_running_state_reports_worker_not_confirmed_until_started(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
            task_id="pending-task",
            started_at=None,
        )
        response = self.client.get(
            reverse("initial_candle_backfill"),
            {"format": "json", "scope": "initial"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()["initial"]
        self.assertEqual(payload["worker_state"], "DISPATCHING")
        self.assertFalse(payload["live"])
        self.assertEqual(payload["progress"]["work_total"], 0)
        self.assertEqual(payload["duration_seconds"], 0)
        self.assertEqual(payload["task_id"], run.task_id)


    def test_json_page_does_not_publish_or_recover_stale_dispatch(self):
        run = CandleBackfillRun.objects.create(
            scope="initial",
            status="running",
            count=5000,
            task_id="stale-task",
        )
        CandleBackfillRun.objects.filter(pk=run.pk).update(
            requested_at=timezone.now() - timedelta(minutes=3),
        )
        with patch("apps.market_data.tasks.run_initial_candle_backfill.apply_async") as publish:
            response = self.client.get(
                reverse("initial_candle_backfill"),
                {"format": "json", "scope": "initial"},
            )
        self.assertEqual(response.status_code, 200)
        run.refresh_from_db()
        self.assertEqual(run.task_id, "stale-task")
        self.assertIsNone(run.started_at)
        publish.assert_not_called()
