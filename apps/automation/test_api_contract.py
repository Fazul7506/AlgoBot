from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from .api import _safe_payload, approve
from .models import ApprovalRequest, Workflow


class AutomationApprovalApiContractTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="automation-owner", password="test-password"
        )
        self.other_user = get_user_model().objects.create_user(
            username="other-automation-owner", password="test-password"
        )
        self.workflow = Workflow.objects.create(user=self.user, name="Approval workflow")
        self.approval = ApprovalRequest.objects.create(
            workflow=self.workflow, requested_by=self.user
        )
        self.factory = APIRequestFactory()

    def _post(self, user, payload):
        request = self.factory.post("/api/automation/approve/", payload, format="json")
        force_authenticate(request, user=user)
        return approve(request)

    def test_missing_approval_id_returns_validation_error(self):
        result = self._post(self.user, {})
        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.data["code"], "APPROVAL_ID_REQUIRED")

    def test_non_finite_payload_values_are_normalized_before_json_persistence(self):
        import math

        cleaned = _safe_payload({"nested": [float("nan"), float("inf"), 3.0]})

        self.assertIsNone(cleaned["nested"][0])
        self.assertIsNone(cleaned["nested"][1])
        self.assertTrue(math.isfinite(cleaned["nested"][2]))

    def test_other_users_approval_is_not_disclosed(self):
        result = self._post(self.other_user, {"approval": self.approval.pk})
        self.assertEqual(result.status_code, 404)

    def test_non_pending_approval_cannot_be_approved_twice(self):
        self.approval.status = "approved"
        self.approval.save(update_fields=["status"])
        result = self._post(self.user, {"approval": self.approval.pk})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "APPROVAL_NOT_PENDING")

    def test_pending_owned_approval_can_be_approved(self):
        result = self._post(self.user, {"approval": self.approval.pk})
        self.assertEqual(result.status_code, 200)
        self.approval.refresh_from_db()
        self.assertEqual(self.approval.status, "approved")
        self.assertEqual(self.approval.approved_by_id, self.user.pk)
