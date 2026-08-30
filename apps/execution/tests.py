from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIRequestFactory, force_authenticate

from .serializers import OrderSerializer
from .views import OrderViewSet


class OrderSerializerRegressionTests(APITestCase):
    def test_terminal_order_values_are_normalized(self):
        serializer = OrderSerializer()
        self.assertEqual(serializer.validate_direction('BUY'), 'buy')
        self.assertEqual(serializer.validate_direction('sell'), 'sell')
        self.assertEqual(serializer.validate_order_type('MARKET'), 'market')
        self.assertEqual(serializer.validate_order_type('limit'), 'limit')

    def test_preview_converts_unexpected_internal_failure_to_structured_503(self):
        user = get_user_model().objects.create_user(username='preview-regression', password='test-password')
        request = APIRequestFactory().post('/api/orders/preview/', {'symbol': '1HZ100V', 'direction': 'buy', 'order_type': 'market', 'stake': '1'}, format='json')
        force_authenticate(request, user=user)
        view = OrderViewSet.as_view({'post': 'preview'})
        with patch.object(OrderSerializer, 'is_valid', side_effect=RuntimeError('synthetic preview failure')):
            result = view(request)
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.data['code'], 'PREVIEW_INTERNAL_ERROR')
        self.assertEqual(result.data['status'], 'rejected')
