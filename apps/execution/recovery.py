"""Execution recovery for requests that became ambiguous at the network boundary."""
from __future__ import annotations

from asgiref.sync import sync_to_async
from django.db import close_old_connections, transaction
from django.utils import timezone

from . import constants as c


class ExecutionRecoveryService:
    """Resolve sent-but-unconfirmed orders from the authoritative broker."""

    async def recover_account(self, account) -> dict:
        from apps.brokers.services import BrokerRegistry

        adapter = BrokerRegistry().adapter(account.broker, account)
        orders = await sync_to_async(list)(
            self._candidate_orders(account)
        )
        recovered = 0
        unresolved = 0
        for order in orders:
            if not order.broker_reference:
                await sync_to_async(self._record_unresolved)(order, "missing_broker_reference")
                unresolved += 1
                continue
            try:
                contract = await adapter._request(
                    {"proposal_open_contract": 1, "contract_id": int(order.broker_reference)},
                    authenticated=True,
                )
                payload = contract.get("proposal_open_contract") or {}
                if payload.get("contract_id"):
                    from .reconciliation import reconcile_execution_event

                    await sync_to_async(reconcile_execution_event)(
                        user=order.user,
                        event={"proposal_open_contract": payload},
                    )
                    recovered += 1
                else:
                    await sync_to_async(self._record_unresolved)(order, "broker_contract_not_found")
                    unresolved += 1
            except Exception as exc:
                await sync_to_async(self._record_unresolved)(order, "broker_lookup_failed", str(exc))
                unresolved += 1
        return {
            "status": "success",
            "account_id": account.account_id,
            "candidates": len(orders),
            "recovered": recovered,
            "unresolved": unresolved,
            "timestamp": timezone.now().isoformat(),
        }

    @staticmethod
    def _candidate_orders(account):
        close_old_connections()
        from .models import Order

        return (
            Order.objects.select_related("user", "broker_account")
            .filter(
                broker_account=account,
                status=c.ORDER_STATUS_SENT,
            )
            .order_by("created_at")
        )

    @staticmethod
    @transaction.atomic
    def _record_unresolved(order, reason, error=None):
        from .models import ReconciliationEvent

        ReconciliationEvent.objects.create(
            user=order.user,
            broker_account=order.broker_account,
            discrepancy_type="ambiguous_execution",
            broker_reference=order.broker_reference,
            symbol=order.symbol,
            summary="Broker execution requires reconciliation",
            details={
                "reason": reason,
                "error": error,
                "order_id": order.pk,
                "client_request_id": order.client_request_id,
                "detected_at": timezone.now().isoformat(),
            },
        )
