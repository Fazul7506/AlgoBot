from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Optional

from django.utils import timezone
from trading.models import Trade
from trading.models.logging import TradeLog, ErrorLog

logger = logging.getLogger(__name__)


class ContractExecutionService:
    """Persist broker-confirmed contract lifecycle events.

    This service intentionally fails closed. It never invents contract IDs,
    prices, payouts or fills when a broker client is unavailable.
    """

    def __init__(self, deriv_client=None):
        self.deriv_client = deriv_client

    def _call(self, method, **kwargs):
        result = method(**kwargs)
        return asyncio.run(result) if inspect.isawaitable(result) else result

    def buy_contract(self, user, symbol: str, contract_type: str, stake: float, trade: Optional[Trade] = None, metadata: dict = None) -> Optional[dict]:
        try:
            if self.deriv_client is None:
                raise RuntimeError("No broker client configured; refusing simulated contract execution")
            if not hasattr(self.deriv_client, "buy_contract"):
                raise RuntimeError("Configured broker client does not support contract purchase")
            broker_result = self._call(
                self.deriv_client.buy_contract,
                symbol=symbol,
                contract_type=contract_type,
                stake=stake,
            )
            if not isinstance(broker_result, dict):
                raise RuntimeError("Broker returned an invalid contract response")
            buy = broker_result.get("buy", broker_result)
            contract_id = buy.get("contract_id") or broker_result.get("contract_id")
            if not contract_id:
                raise RuntimeError("Broker did not return a contract ID")
            result = {
                "contract_id": str(contract_id),
                "symbol": symbol,
                "contract_type": contract_type,
                "stake": stake,
                "entry_price": buy.get("entry_spot", buy.get("spot", 0)),
                "entry_time": timezone.now(),
                "payout": buy.get("payout"),
                "status": "OPEN",
                "raw": broker_result,
            }
            TradeLog.objects.create(user=user, action="OPEN", symbol=symbol, contract_type=contract_type, stake=stake, message=f"Contract opened: {contract_id}", metadata=metadata or {})
            return result
        except Exception as exc:
            logger.error("Contract buy failed", exc_info=True)
            ErrorLog.objects.create(user=user, error_type="CONTRACT_BUY_FAILED", severity="ERROR", message=str(exc))
            return None

    def close_contract(self, user, contract_id: str, exit_price: float, trade: Optional[Trade] = None, metadata: dict = None) -> bool:
        try:
            if self.deriv_client is None or not hasattr(self.deriv_client, "sell_contract"):
                raise RuntimeError("No broker client configured; refusing simulated contract close")
            broker_result = self._call(self.deriv_client.sell_contract, contract_id=contract_id)
            if not isinstance(broker_result, dict) or broker_result.get("error"):
                raise RuntimeError("Broker rejected contract close")
            if trade:
                trade.status = "CLOSED"
                trade.exit_price = exit_price
                trade.closed_at = timezone.now()
                trade.save(update_fields=["status", "exit_price", "closed_at"])
            TradeLog.objects.create(user=user, action="CLOSE", symbol=trade.symbol if trade else "UNKNOWN", contract_type=trade.contract_type if trade else "UNKNOWN", stake=trade.stake if trade else 0, message=f"Contract closed: {contract_id} at {exit_price}", metadata={**(metadata or {}), "broker_response": broker_result})
            return True
        except Exception as exc:
            logger.error("Contract close failed", exc_info=True)
            return False
