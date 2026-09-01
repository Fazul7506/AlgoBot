from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from apps.execution.views import OrderViewSet


class TerminalOrderFailureTests(APIView):
    """Regression helpers for the terminal order endpoint."""


class TestTerminalOrderFailureNormalization:
    def test_demo_execution_exception_returns_json_503(self, db):
        user = get_user_model().objects.create_user(username="terminal-test", password="x")
        account = SimpleNamespace(
            id=7,
            credentials={"account_type": "demo"},
            user_id=user.id,
            is_connection_eligible=True,
            is_preferred=True,
        )
        factory = APIRequestFactory()
        request = factory.post(
            "/api/orders/",
            {
                "broker_account": account.id,
                "symbol": "1HZ100V",
                "direction": "buy",
                "order_type": "market",
                "stake": "1",
                "client_request_id": "terminal-test-1",
            },
            format="json",
        )
        force_authenticate(request, user=user)
        with patch.object(OrderViewSet, "get_serializer") as serializer_factory:
            serializer = serializer_factory.return_value
            serializer.is_valid.return_value = True
            serializer.validated_data = {
                "broker_account": account,
                "symbol": "1HZ100V",
                "direction": "buy",
                "order_type": "market",
                "stake": "1",
                "client_request_id": "terminal-test-1",
                "strategy": "",
            }
            with patch("apps.execution.views.ExecutionEngine.place_order", side_effect=RuntimeError("broker path failed")):
                result = OrderViewSet.as_view({"post": "create"})(request)

        assert result.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert result.data["code"] == "EXECUTION_UNAVAILABLE"
        assert result.data["retryable"] is False
        assert "broker path failed" in result.data["detail"]
