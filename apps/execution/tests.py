from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.brokers.models import BrokerAccount
from .serializers import OrderSerializer


class OrderSerializerRegressionTests(APITestCase):
    def test_direction_is_normalized_from_terminal_buy_sell(self):
        serializer = OrderSerializer(data={
            'broker_account': 1,
            'symbol': 'frxXAGUSD',
            'direction': 'BUY',
            'order_type': 'MARKET',
            'stake': '1',
            'strategy': '',
            'client_request_id': 'regression-buy-001',
            'validation_context': {},
        })
        # The foreign-key value is deliberately not validated here; this test
        # only guards the API-boundary normalization contract.
        try:
            serializer.fields['direction'].run_validation('BUY')
            serializer.fields['order_type'].run_validation('MARKET')
        except Exception as exc:
            self.fail(f'Order terminal normalization regressed: {exc}')
        self.assertEqual(serializer.validate_direction('BUY'), 'buy')
        self.assertEqual(serializer.validate_order_type('MARKET'), 'market')
