from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]
PYTHON_WORKFLOWS = (
    ".github/workflows/phase20-production.yml",
    ".github/workflows/frontend-hardening.yml",
    ".github/workflows/template-validation.yml",
    ".github/workflows/rebuild-all-django-migrations.yml",
    ".github/workflows/broker-adapter-validation.yml",
    ".github/workflows/broker-onboarding-pipeline.yml",
    ".github/workflows/broker-proposal-pr.yml",
    ".github/workflows/deriv-demo-sandbox-verification.yml",
    ".github/workflows/scheduled-project-health-audit.yml",
)


class PythonRuntimePinTests(SimpleTestCase):
    def test_render_python_runtime_matches_the_tested_tensorflow_runtime(self):
        self.assertEqual((ROOT / ".python-version").read_text().strip(), "3.13.15")
        requirements = (ROOT / "requirements/base.txt").read_text()
        self.assertIn("tensorflow>=2.20,<2.21", requirements)
        render = (ROOT / "render.yaml").read_text()
        self.assertIn(".python-version", render)
        self.assertNotIn("key: PYTHON_VERSION", render)

    def test_python_workflows_use_the_repository_runtime_pin(self):
        for relative_path in PYTHON_WORKFLOWS:
            with self.subTest(workflow=relative_path):
                workflow = (ROOT / relative_path).read_text()
                self.assertIn('python-version-file: ".python-version"', workflow)
                self.assertNotIn('python-version: "3.13"', workflow)
                self.assertNotIn("python-version: '3.13'", workflow)
