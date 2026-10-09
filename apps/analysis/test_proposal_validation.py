from django.contrib.auth import get_user_model
from django.test import TestCase


class BrokerProposalValidationTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="proposal-validation-test", password="test-password")
        self.client.force_login(user)

    def post_payload(self, payload):
        return self.client.post(
            "/analysis/proposal/",
            data=payload,
            content_type="application/json",
        )

    def test_proposal_rejects_non_object_json(self):
        response = self.post_payload(["R_100", "CALL"])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "INVALID_PROPOSAL_OBJECT")

    def test_proposal_rejects_invalid_confidence_before_broker_io(self):
        response = self.post_payload({"symbol": "R_100", "contract_type": "CALL", "confidence": 101})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "INVALID_CONFIDENCE")

    def test_proposal_rejects_fractional_duration_before_broker_io(self):
        response = self.post_payload({"symbol": "R_100", "contract_type": "CALL", "duration": 1.5})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "INVALID_DURATION")

    def test_proposal_rejects_payout_basis_until_risk_cap_is_payout_aware(self):
        response = self.post_payload({"symbol": "R_100", "contract_type": "CALL", "basis": "payout"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "UNSUPPORTED_PROPOSAL_BASIS")
