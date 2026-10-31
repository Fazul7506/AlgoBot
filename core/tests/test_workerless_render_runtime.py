from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]


class WorkerlessRenderRuntimeContractTests(SimpleTestCase):
    def test_render_defines_only_the_web_service(self):
        blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertNotIn("\n  - type: worker\n", blueprint)
        self.assertIn("bash deploy/web/start.sh", blueprint)

    def test_single_web_runtime_supervises_all_existing_background_responsibilities(self):
        script = (ROOT / "deploy" / "web" / "start.sh").read_text(encoding="utf-8")
        for command in (
            "daphne --bind 0.0.0.0",
            "celery -A deriv_platform.celery worker",
            "celery -A deriv_platform.celery beat",
            "python manage.py run_market_stream",
        ):
            with self.subTest(command=command):
                self.assertIn(command, script)
        self.assertIn("trap stop_children EXIT INT TERM", script)
        self.assertIn("start_worker", script)
        self.assertIn("start_beat", script)
        self.assertIn("start_market_stream", script)
        self.assertIn("DB_POOL_MAX_SIZE", script)
