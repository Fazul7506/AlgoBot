from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.brokers.models import Broker, BrokerAccount
from apps.execution.views import TradeHistoryViewSet


class TradeHistoryFilterValidationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="history-filter-user", password="test-password")
        self.broker = Broker.objects.create(name="Deriv", broker_type="deriv", status="active")
        self.account = BrokerAccount.objects.create(
            user=self.user, broker=self.broker, account_id="VRTC-HISTORY", status="active"
        )
        self.factory = APIRequestFactory()
        self.view = TradeHistoryViewSet.as_view({"get": "list"})

    def request(self, query):
        request = self.factory.get("/api/trade-history/", query)
        force_authenticate(request, user=self.user)
        return request

    def test_invalid_dates_are_rejected_when_using_cached_pagination(self):
        with __import__("unittest").mock.patch(
            "apps.execution.views.get_active_account", return_value=self.account
        ):
            response = self.view(self.request({"refresh": "0", "date_from": "not-a-date"}))
        self.assertEqual(response.status_code, 400)

    def test_reversed_date_range_is_rejected_when_using_cached_pagination(self):
        with __import__("unittest").mock.patch(
            "apps.execution.views.get_active_account", return_value=self.account
        ):
            response = self.view(self.request({
                "refresh": "0", "date_from": "2026-10-08", "date_to": "2026-10-01"
            }))
        self.assertEqual(response.status_code, 400)
