"""Deriv-native trading operations.

This module keeps proposal, buy, open-contract, update, history, sell and
cancel semantics explicit instead of forcing Deriv's contract lifecycle into
a generic broker order abstraction.
"""
from __future__ import annotations

from typing import Any

from .exceptions import BrokerOrderError
from .services import BrokerRegistry


class DerivTradingOperations:
    """Account-scoped implementation of Deriv's trading lifecycle."""

    def __init__(self, account):
        if account is None or account.broker.broker_type != "deriv":
            raise BrokerOrderError("A connected Deriv account is required")
        self.account = account
        self.adapter = BrokerRegistry().adapter(account.broker, account)

    @staticmethod
    def _clean_number(value: Any) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError):
            raise BrokerOrderError("A valid numeric value is required")
        if result <= 0:
            raise BrokerOrderError("The value must be greater than zero")
        return result

    async def contracts_for(self, symbol: str) -> list[dict]:
        symbol = str(symbol or "").strip()
        if not symbol:
            raise BrokerOrderError("A market symbol is required")
        return await self.adapter.get_trade_capabilities(symbol)

    async def proposal(self, *, symbol: str, contract_type: str, amount: Any,
                       currency: str, duration: int, duration_unit: str = "s",
                       basis: str = "stake", barrier: Any = None,
                       multiplier: Any = None, subscribe: bool = True) -> dict:
        symbol = str(symbol or "").strip()
        contract_type = str(contract_type or "").upper().strip()
        if not symbol or not contract_type:
            raise BrokerOrderError("Symbol and contract type are required")
        amount_value = self._clean_number(amount)
        duration = int(duration)
        if duration <= 0:
            raise BrokerOrderError("Duration must be greater than zero")
        payload = {
            "proposal": 1,
            "amount": amount_value,
            "basis": basis or "stake",
            "contract_type": contract_type,
            "currency": str(currency or self.account.currency),
            "duration": duration,
            "duration_unit": str(duration_unit or "s"),
            "underlying_symbol": symbol,
        }
        if subscribe:
            payload["subscribe"] = 1
        if barrier is not None:
            payload["barrier"] = str(barrier)
        if multiplier is not None:
            payload["multiplier"] = float(multiplier)
        response = await self.adapter._request(payload, authenticated=True)
        proposal = response.get("proposal") or {}
        if not proposal.get("id"):
            raise BrokerOrderError("Deriv returned a proposal without an ID")
        return {
            "proposal_id": str(proposal["id"]),
            "ask_price": proposal.get("ask_price"),
            "payout": proposal.get("payout"),
            "spot": proposal.get("spot"),
            "display_value": proposal.get("display_value"),
            "contract_type": contract_type,
            "symbol": symbol,
            "currency": currency,
            "raw": proposal,
        }

    async def buy(self, *, proposal_id: str, price: Any) -> dict:
        proposal_id = str(proposal_id or "").strip()
        if not proposal_id:
            raise BrokerOrderError("A Deriv proposal ID is required")
        price_value = self._clean_number(price)
        response = await self.adapter._request(
            {"buy": proposal_id, "price": price_value}, authenticated=True
        )
        result = response.get("buy") or {}
        contract_id = result.get("contract_id")
        if not contract_id:
            raise BrokerOrderError("Deriv buy response did not contain a contract ID")
        return {
            "status": "filled",
            "contract_id": str(contract_id),
            "transaction_id": result.get("transaction_id"),
            "buy_price": result.get("buy_price"),
            "payout": result.get("payout"),
            "start_time": result.get("start_time"),
            "purchase_time": result.get("purchase_time"),
            "longcode": result.get("longcode"),
            "proposal_id": proposal_id,
            "raw": result,
        }

    async def open_contract(self, contract_id: int | str, subscribe: bool = True) -> dict:
        try:
            contract_id = int(contract_id)
        except (TypeError, ValueError):
            raise BrokerOrderError("A valid Deriv contract ID is required")
        payload = {"proposal_open_contract": 1, "contract_id": contract_id}
        if subscribe:
            payload["subscribe"] = 1
        response = await self.adapter._request(payload, authenticated=True)
        contract = response.get("proposal_open_contract") or {}
        if not contract.get("contract_id"):
            raise BrokerOrderError("Deriv returned no open-contract state")
        return contract

    async def sell(self, *, contract_id: int | str, price: Any = 0) -> dict:
        try:
            contract_id = int(contract_id)
        except (TypeError, ValueError):
            raise BrokerOrderError("A valid Deriv contract ID is required")
        if price in (None, ""):
            price = 0
        price_value = float(price)
        if price_value < 0:
            raise BrokerOrderError("Sell price cannot be negative")
        response = await self.adapter._request(
            {"sell": contract_id, "price": price_value}, authenticated=True
        )
        result = response.get("sell") or {}
        if not result:
            raise BrokerOrderError("Deriv returned an empty sell response")
        return result

    async def update(self, *, contract_id: int | str, changes: dict) -> dict:
        try:
            contract_id = int(contract_id)
        except (TypeError, ValueError):
            raise BrokerOrderError("A valid Deriv contract ID is required")
        if not isinstance(changes, dict) or not changes:
            raise BrokerOrderError("At least one contract update is required")
        payload = {"contract_update": 1, "contract_id": contract_id, **changes}
        response = await self.adapter._request(payload, authenticated=True)
        return response.get("contract_update") or response

    async def update_history(self, contract_id: int | str) -> dict:
        try:
            contract_id = int(contract_id)
        except (TypeError, ValueError):
            raise BrokerOrderError("A valid Deriv contract ID is required")
        response = await self.adapter._request(
            {"contract_update_history": 1, "contract_id": contract_id}, authenticated=True
        )
        return response.get("contract_update_history") or response

    async def cancel(self, contract_id: int | str) -> dict:
        try:
            contract_id = int(contract_id)
        except (TypeError, ValueError):
            raise BrokerOrderError("A valid Deriv contract ID is required")
        response = await self.adapter._request(
            {"cancel": 1, "contract_id": contract_id}, authenticated=True
        )
        return response.get("cancel") or response
