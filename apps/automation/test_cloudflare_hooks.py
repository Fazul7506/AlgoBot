import json
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase

from apps.automation.cloudflare_hooks import cloudflare_task_dispatch


class CloudflareTaskDispatchTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.headers = {"HTTP_AUTHORIZATION": "Bearer test-secret"}

    @patch.dict("os.environ", {"CLOUDFLARE_TASK_DISPATCH_TOKEN": "test-secret"})
    @patch("apps.automation.cloudflare_hooks.cache")
    @patch("apps.automation.cloudflare_hooks.current_app")
    def test_valid_allowlisted_task_is_queued(self, celery, cache):
        cache.add.return_value = True
        celery.send_task.return_value = Mock(id="celery-task-123")
        request = self.factory.post(
            "/api/internal/cloudflare/task-dispatch/",
            data=json.dumps({
                "schedule_id": "ai-data-health-every-15-minutes",
                "task": "apps.ai_engine.tasks.check_ai_data_health",
                "kwargs": {"timeframe": "M1"},
                "scheduled_minute": 29_999_999,
            }),
            content_type="application/json",
            **self.headers,
        )
        response = cloudflare_task_dispatch(request)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(json.loads(response.content)["status"], "queued")
        celery.send_task.assert_called_once_with(
            "apps.ai_engine.tasks.check_ai_data_health",
            kwargs={"timeframe": "M1"},
            queue="celery",
        )


    @patch.dict("os.environ", {"CLOUDFLARE_TASK_DISPATCH_TOKEN": "test-secret"})
    def test_oversized_task_dispatch_payload_is_rejected(self):
        from apps.automation.cloudflare_hooks import MAX_TASK_DISPATCH_BODY_BYTES

        request = self.factory.post(
            "/api/internal/cloudflare/task-dispatch/",
            data=b"x" * (MAX_TASK_DISPATCH_BODY_BYTES + 1),
            content_type="application/json",
            **self.headers,
        )
        response = cloudflare_task_dispatch(request)
        self.assertEqual(response.status_code, 413)

    def test_missing_token_is_rejected(self):
        request = self.factory.post(
            "/api/internal/cloudflare/task-dispatch/",
            data="{}",
            content_type="application/json",
        )
        with patch.dict("os.environ", {"CLOUDFLARE_TASK_DISPATCH_TOKEN": ""}):
            response = cloudflare_task_dispatch(request)
        self.assertEqual(response.status_code, 401)

    @patch.dict("os.environ", {"CLOUDFLARE_TASK_DISPATCH_TOKEN": "test-secret"})
    def test_unapproved_task_is_rejected(self):
        request = self.factory.post(
            "/api/internal/cloudflare/task-dispatch/",
            data=json.dumps({
                "schedule_id": "arbitrary",
                "task": "os.system",
                "kwargs": {},
                "scheduled_minute": 10,
            }),
            content_type="application/json",
            **self.headers,
        )
        response = cloudflare_task_dispatch(request)
        self.assertEqual(response.status_code, 400)

    @patch.dict("os.environ", {"CLOUDFLARE_TASK_DISPATCH_TOKEN": "test-secret"})
    @patch("apps.automation.cloudflare_hooks.cache")
    @patch("apps.automation.cloudflare_hooks.current_app")
    def test_queue_redelivery_is_idempotently_accepted(self, celery, cache):
        cache.add.return_value = False
        request = self.factory.post(
            "/api/internal/cloudflare/task-dispatch/",
            data=json.dumps({
                "schedule_id": "ai-data-health-every-15-minutes",
                "task": "apps.ai_engine.tasks.check_ai_data_health",
                "kwargs": {"timeframe": "M1"},
                "scheduled_minute": 29_999_999,
            }),
            content_type="application/json",
            **self.headers,
        )
        response = cloudflare_task_dispatch(request)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(json.loads(response.content)["status"], "duplicate")
        celery.send_task.assert_not_called()

    def test_unhashable_task_name_is_rejected(self):
        request = self.factory.post(
            "/api/internal/cloudflare/task-dispatch/",
            data=json.dumps({
                "schedule_id": "ai-data-health-every-15-minutes",
                "task": ["apps.ai_engine.tasks.check_ai_data_health"],
                "kwargs": {},
                "scheduled_minute": 10,
            }),
            content_type="application/json",
            **self.headers,
        )
        with patch.dict("os.environ", {"CLOUDFLARE_TASK_DISPATCH_TOKEN": "test-secret"}):
            response = cloudflare_task_dispatch(request)
        self.assertEqual(response.status_code, 400)

    @patch.dict("os.environ", {"CLOUDFLARE_TASK_DISPATCH_TOKEN": "test-secret"})
    def test_schedule_cannot_dispatch_a_different_allowlisted_task(self):
        request = self.factory.post(
            "/api/internal/cloudflare/task-dispatch/",
            data=json.dumps({
                "schedule_id": "ai-data-health-every-15-minutes",
                "task": "apps.execution.process_execution_queue",
                "kwargs": {"batch_size": 10},
                "scheduled_minute": 10,
            }),
            content_type="application/json",
            **self.headers,
        )
        response = cloudflare_task_dispatch(request)
        self.assertEqual(response.status_code, 400)

    @patch.dict("os.environ", {"CLOUDFLARE_TASK_DISPATCH_TOKEN": "test-secret"})
    @patch("apps.automation.cloudflare_hooks.cache")
    @patch("apps.automation.cloudflare_hooks.current_app")
    def test_ai_training_is_dispatched_through_unified_allowlist(self, celery, cache):
        cache.add.return_value = True
        celery.send_task.return_value = Mock(id="celery-ai-training")
        request = self.factory.post(
            "/api/internal/cloudflare/task-dispatch/",
            data=json.dumps({
                "schedule_id": "ai-training-every-6-hours",
                "task": "apps.ai_engine.tasks.scheduled_ai_training",
                "kwargs": {"timeframe": "M1", "min_accuracy": 0.52},
                "scheduled_minute": 29_999_999,
            }),
            content_type="application/json",
            **self.headers,
        )
        response = cloudflare_task_dispatch(request)
        self.assertEqual(response.status_code, 202)
        celery.send_task.assert_called_once_with(
            "apps.ai_engine.tasks.scheduled_ai_training",
            kwargs={"timeframe": "M1", "min_accuracy": 0.52},
            queue="celery",
        )

    @patch.dict("os.environ", {"CLOUDFLARE_TASK_DISPATCH_TOKEN": "test-secret"})
    def test_ai_training_rejects_out_of_range_min_accuracy(self):
        request = self.factory.post(
            "/api/internal/cloudflare/task-dispatch/",
            data=json.dumps({
                "schedule_id": "ai-training-every-6-hours",
                "task": "apps.ai_engine.tasks.scheduled_ai_training",
                "kwargs": {"timeframe": "M1", "min_accuracy": 2.0},
                "scheduled_minute": 29_999_999,
            }),
            content_type="application/json",
            **self.headers,
        )
        response = cloudflare_task_dispatch(request)
        self.assertEqual(response.status_code, 400)
