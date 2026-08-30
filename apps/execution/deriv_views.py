from asgiref.sync import async_to_sync
from rest_framework import permissions, response, status, views

from apps.brokers.deriv_execution import DerivTradingOperations
from apps.brokers.exceptions import BrokerOrderError
from apps.brokers.models import BrokerAccount


class DerivTradingActionView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _account(self, request):
        account_id = request.data.get("broker_account_id") or request.query_params.get("broker_account_id")
        if not account_id:
            raise BrokerOrderError("broker_account_id is required")
        account = BrokerAccount.objects.select_related("broker").filter(
            pk=account_id, user=request.user, status="active", broker__broker_type="deriv"
        ).first()
        if account is None or not account.is_connection_eligible:
            raise BrokerOrderError("The selected Deriv account is not connected or is not usable")
        return account

    def _execute(self, request, operation):
        try:
            account = self._account(request)
            result = operation(DerivTradingOperations(account))
            return response.Response(result, status=status.HTTP_200_OK)
        except BrokerOrderError as exc:
            return response.Response(
                {"status": "rejected", "code": "DERIV_TRADE_REJECTED", "detail": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )

    def post(self, request, action):
        if action == "proposal":
            return self._execute(request, lambda ops: async_to_sync(ops.proposal)(
                symbol=request.data.get("symbol"),
                contract_type=request.data.get("contract_type"),
                amount=request.data.get("amount", request.data.get("stake")),
                currency=request.data.get("currency"),
                duration=request.data.get("duration", 60),
                duration_unit=request.data.get("duration_unit", "s"),
                basis=request.data.get("basis", "stake"),
                barrier=request.data.get("barrier"),
                multiplier=request.data.get("multiplier"),
                subscribe=bool(request.data.get("subscribe", True)),
            ))
        if action == "buy":
            return self._execute(request, lambda ops: async_to_sync(ops.buy)(
                proposal_id=request.data.get("proposal_id"), price=request.data.get("price")
            ))
        if action == "open-contract":
            return self._execute(request, lambda ops: async_to_sync(ops.open_contract)(
                request.data.get("contract_id"), bool(request.data.get("subscribe", True))
            ))
        if action == "sell":
            return self._execute(request, lambda ops: async_to_sync(ops.sell)(
                contract_id=request.data.get("contract_id"), price=request.data.get("price", 0)
            ))
        if action == "update":
            return self._execute(request, lambda ops: async_to_sync(ops.update)(
                contract_id=request.data.get("contract_id"), changes=request.data.get("changes") or {}
            ))
        if action == "update-history":
            return self._execute(request, lambda ops: async_to_sync(ops.update_history)(request.data.get("contract_id")))
        if action == "cancel":
            return self._execute(request, lambda ops: async_to_sync(ops.cancel)(request.data.get("contract_id")))
        return response.Response({"status": "rejected", "code": "UNKNOWN_DERIV_ACTION"}, status=status.HTTP_404_NOT_FOUND)

    def get(self, request, action):
        if action == "contracts-for":
            try:
                account = self._account(request)
                symbol = request.query_params.get("symbol")
                return response.Response(async_to_sync(DerivTradingOperations(account).contracts_for)(symbol))
            except BrokerOrderError as exc:
                return response.Response({"status": "rejected", "code": "DERIV_TRADE_REJECTED", "detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return response.Response({"status": "rejected", "code": "UNKNOWN_DERIV_ACTION"}, status=status.HTTP_404_NOT_FOUND)
