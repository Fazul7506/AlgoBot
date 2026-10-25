from unittest import TestCase

from apps.brokers.project_manager_agent import _is_allowed_path


class ProjectManagerPathGuardTests(TestCase):
    def test_application_source_paths_are_allowed(self):
        self.assertTrue(_is_allowed_path("apps/dashboard/views.py"))
        self.assertTrue(_is_allowed_path("templates/dashboard.html"))

    def test_sensitive_and_operational_paths_are_rejected(self):
        self.assertFalse(_is_allowed_path("../settings.py", allow_new=True))
        self.assertFalse(_is_allowed_path(".github/workflows/deploy.yml", allow_new=True))
        self.assertFalse(_is_allowed_path("apps/accounts/migrations/0001_initial.py", allow_new=True))
        self.assertFalse(_is_allowed_path("apps/core/.env.production", allow_new=True))
        self.assertFalse(_is_allowed_path("requirements.txt", allow_new=True))

    def test_new_files_are_limited_to_application_source_areas(self):
        self.assertTrue(_is_allowed_path("apps/new_feature/service.py", allow_new=True))
        self.assertFalse(_is_allowed_path("docs/new-feature.md", allow_new=True))
