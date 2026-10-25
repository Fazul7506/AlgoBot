from unittest import TestCase

from apps.brokers.project_manager_agent import _is_allowed_path


class ProjectManagerPathGuardTests(TestCase):
    def test_application_and_project_configuration_paths_are_allowed(self):
        self.assertTrue(_is_allowed_path("apps/dashboard/views.py"))
        self.assertTrue(_is_allowed_path("templates/dashboard.html"))
        self.assertTrue(_is_allowed_path("docs/new-feature.md", allow_new=True))
        self.assertTrue(_is_allowed_path(".github/workflows/quality.yml", allow_new=True))
        self.assertTrue(_is_allowed_path("apps/accounts/migrations/0001_initial.py", allow_new=True))
        self.assertTrue(_is_allowed_path("requirements.txt", allow_new=True))
        self.assertTrue(_is_allowed_path("config/settings/base.py", allow_new=True))
        self.assertTrue(_is_allowed_path("Dockerfile", allow_new=True))

    def test_traversal_and_sensitive_paths_are_rejected(self):
        self.assertFalse(_is_allowed_path("../settings.py", allow_new=True))
        self.assertFalse(_is_allowed_path("apps/core/.env.production", allow_new=True))
        self.assertFalse(_is_allowed_path("secrets/production.json", allow_new=True))
        self.assertFalse(_is_allowed_path("credentials/private_keys/id_rsa", allow_new=True))
        self.assertFalse(_is_allowed_path("node_modules/package/index.js", allow_new=True))

    def test_new_files_can_be_created_in_any_non_sensitive_project_area(self):
        self.assertTrue(_is_allowed_path("apps/new_feature/service.py", allow_new=True))
        self.assertTrue(_is_allowed_path("docs/new-feature.md", allow_new=True))
        self.assertTrue(_is_allowed_path("infra/terraform/main.tf", allow_new=True))
