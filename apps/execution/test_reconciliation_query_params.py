from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.brokers.models import Broker, BrokerAccount
from apps.execution.models import ReconciliationEvent
from apps.execution.views import ReconciliationEventViewSet


class ReconciliationQueryParameterRegressionTests(TestCase):
    def test_reconciliation_list_uses_django_get_parameters(self):
        user = get_user_model().objects.create_user(
            username="reconciliation-query-regression",
            password="test-password",
        )
        broker = Broker.objects.create(
            name="Reconciliation Broker",
            broker_type="paper",
            status="active",
            supports_live=False,
        )
        account = BrokerAccount.objects.create(
            user=user,
            broker=broker,
            account_id="RECON",
            status="active",
            credentials={"account_type": "demo"},
        )
        ReconciliationEvent.objects.create(
            user=user,
            broker_account=account,
            status=ReconciliationEvent.STATUS_OPEN,
            discrepancy_type="test",
            broker_reference="REF-1",
            symbol="R_100",
            summary="Open discrepancy",
        )
        ReconciliationEvent.objects.create(
            user=user,
            broker_account=account,
            status=ReconciliationEvent.STATUS_REVIEWED,
            discrepancy_type="test",
            broker_reference="REF-2",
            symbol="R_100",
            summary="Reviewed discrepancy",
        )

        request = APIRequestFactory().get(
            f"/api/reconciliation/events/?status=open&broker_account={account.pk}"
        )
        force_authenticate(request, user=user)
        result = ReconciliationEventViewSet.as_view({"get": "list"})(request)

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(result.data["results"][0]["broker_reference"], "REF-1")
