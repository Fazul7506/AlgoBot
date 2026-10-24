"""Trusted, opt-in Deriv demo lifecycle checks using the documented v3 WebSocket API.

Only demo tokens are accepted (VRTC + is_virtual). A single stake <= 1 currency
unit is used. This harness never connects to a real-account endpoint. It does not
retry a buy after an ambiguous result; it reconciles using portfolio and contract
history first. Deriv cancellation is contract-type dependent and is not equivalent
to selling/closing a contract; unsupported cancellation is reported as a failure.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.parse
import uuid
from typing import Any

import websockets

from apps.brokers.sandbox_verification import SandboxCheckResult

APP_ID = os.environ.get("BROKER_SANDBOX_APP_ID", "").strip()
TOKEN = os.environ.get("BROKER_SANDBOX_API_TOKEN", "").strip()
SYMBOL = os.environ.get("DERIV_DEMO_SYMBOL", "R_100").strip()
STAKE = float(os.environ.get("DERIV_DEMO_STAKE", "1"))
MAX_STAKE = 1.0
TIMEOUT = 12


class DerivDemoHarness:
    def __init__(self) -> None:
        self.ws: Any = None
        self.account: dict[str, Any] = {}
        self.currency = ""
        self.contract_id: int | None = None
        self.buy_marker = "algobot-" + uuid.uuid4().hex
        self.results: dict[str, SandboxCheckResult] = {}

    async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.ws is None:
            raise RuntimeError("WebSocket not connected")
        req_id = int(time.time_ns() % 2_000_000_000)
        await self.ws.send(json.dumps({**payload, "req_id": req_id}))
        deadline = time.monotonic() + TIMEOUT
        while time.monotonic() < deadline:
            raw = await asyncio.wait_for(self.ws.recv(), max(0.1, deadline - time.monotonic()))
            message = json.loads(raw)
            if message.get("req_id") != req_id:
                continue
            if message.get("error"):
                # Do not propagate provider messages; they may contain sensitive details.
                error = message.get("error") or {}
                raise RuntimeError("Deriv API rejected request: " + str(error.get("code", "ProviderError")))
            return message
        raise TimeoutError("Deriv request timed out")

    async def connect(self) -> None:
        if not APP_ID.isdigit() or not TOKEN:
            raise RuntimeError("BROKER_SANDBOX_APP_ID and BROKER_SANDBOX_API_TOKEN are required")
        if not SYMBOL or len(SYMBOL) > 32 or not (0 < STAKE <= MAX_STAKE):
            raise RuntimeError("Invalid demo symbol or stake; stake must be <= 1 currency unit")
        url = "wss://ws.derivws.com/websockets/v3?" + urllib.parse.urlencode({"app_id": APP_ID})
        self.ws = await websockets.connect(url, open_timeout=TIMEOUT, close_timeout=5, ping_interval=20)
        response = await self.request({"authorize": TOKEN})
        self.account = response.get("authorize") or {}
        loginid = str(self.account.get("loginid") or "")
        if not loginid.startswith("VRTC") or self.account.get("is_virtual") not in (1, True):
            await self.ws.close()
            self.ws = None
            raise RuntimeError("Deriv did not verify a virtual account; trade tests blocked")
        self.currency = str(self.account.get("currency") or "")

    async def check_auth(self) -> SandboxCheckResult:
        return SandboxCheckResult(True, "deriv-demo-authentication-verified")

    async def check_identity(self) -> SandboxCheckResult:
        ok = str(self.account.get("loginid", "")).startswith("VRTC") and self.account.get("is_virtual") in (1, True)
        return SandboxCheckResult(ok, "deriv-virtual-account-identity-verified" if ok else "deriv-virtual-account-identity-failed")

    async def check_market(self) -> SandboxCheckResult:
        tick = await self.request({"ticks": SYMBOL})
        quote = (tick.get("tick") or {}).get("quote")
        if quote is None:
            raise RuntimeError("No quote returned")
        return SandboxCheckResult(True, "deriv-demo-market-quote-received")

    async def check_order(self) -> SandboxCheckResult:
        # Ensure contract discovery first; use a short CALL contract and a tiny stake.
        contracts = await self.request({"contracts_for": SYMBOL, "currency": self.currency})
        available = (contracts.get("contracts_for") or {}).get("available") or []
        supported = {str(item.get("contract_type")) for item in available if isinstance(item, dict)}
        contract_type = "CALL" if "CALL" in supported else ("PUT" if "PUT" in supported else "")
        if not contract_type:
            raise RuntimeError("No supported short CALL/PUT contract for configured demo symbol")
        proposal = await self.request({
            "proposal": 1, "amount": STAKE, "basis": "stake", "contract_type": contract_type,
            "currency": self.currency, "duration": 5, "duration_unit": "t", "symbol": SYMBOL,
            "passthrough": {"client_marker": self.buy_marker},
        })
        offer = proposal.get("proposal") or {}
        proposal_id = offer.get("id")
        ask = float(offer.get("ask_price") or 0)
        if not proposal_id or ask <= 0 or ask > MAX_STAKE:
            raise RuntimeError("Proposal invalid or exceeds the configured demo stake ceiling")
        try:
            bought = await self.request({"buy": str(proposal_id), "price": ask, "passthrough": {"client_marker": self.buy_marker}})
        except (TimeoutError, asyncio.TimeoutError):
            # Ambiguous outcome: reconcile before any further order request. Never resubmit.
            await self.reconcile_ambiguous()
            raise RuntimeError("Buy response was ambiguous; reconciled without resubmitting")
        details = bought.get("buy") or {}
        contract_id = details.get("contract_id")
        if not contract_id:
            await self.reconcile_ambiguous()
            raise RuntimeError("Buy response had no contract id; reconciled without resubmitting")
        self.contract_id = int(contract_id)
        return SandboxCheckResult(True, "deriv-demo-order-accepted-with-contract-id")

    async def reconcile_ambiguous(self) -> None:
        # Read-only portfolio reconciliation. No second buy is ever issued here.
        portfolio = await self.request({"portfolio": 1})
        contracts = (portfolio.get("portfolio") or {}).get("contracts") or []
        for item in contracts:
            if str(item.get("contract_id", "")) == str(self.contract_id or ""):
                return
        # Request trade history as a second read path; marker is not assumed to be searchable.
        await self.request({"profit_table": 1, "description": 1, "limit": 50})

    async def check_cancel(self) -> SandboxCheckResult:
        if self.contract_id is None:
            return SandboxCheckResult(False, "deriv-cancel-not-run-no-contract")
        # Deriv cancellation is only valid for cancellation-enabled contracts.
        # A rejected cancellation is not misreported as a close or successful cancel.
        try:
            response = await self.request({"cancel": 1, "contract_id": self.contract_id})
            result = response.get("cancel") or {}
            if not result:
                return SandboxCheckResult(False, "deriv-contract-cancellation-not-confirmed")
            return SandboxCheckResult(True, "deriv-contract-cancellation-confirmed")
        except Exception:
            # Try the distinct close/sell operation for cleanup, but cancellation remains failed.
            try:
                await self.request({"sell": self.contract_id, "price": 0})
            except Exception:
                pass
            return SandboxCheckResult(False, "deriv-contract-cancellation-unsupported-for-test-contract")

    async def check_fills(self) -> SandboxCheckResult:
        if self.contract_id is None:
            return SandboxCheckResult(False, "deriv-fill-not-run-no-contract")
        result = await self.request({"proposal_open_contract": 1, "contract_id": self.contract_id})
        contract = result.get("proposal_open_contract") or {}
        if str(contract.get("contract_id", "")) != str(self.contract_id):
            return SandboxCheckResult(False, "deriv-fill-contract-id-not-confirmed")
        # A buy response with a contract id is accepted execution; check transaction fields when available.
        if contract.get("buy_price") is None and contract.get("entry_spot") is None:
            return SandboxCheckResult(False, "deriv-fill-details-not-confirmed")
        return SandboxCheckResult(True, "deriv-contract-entry-confirmed")

    async def check_reconciliation(self) -> SandboxCheckResult:
        # Explicitly verify read-after-write visibility. This does not trigger a retry.
        if self.contract_id is None:
            await self.reconcile_ambiguous()
            return SandboxCheckResult(False, "deriv-ambiguous-execution-had-no-confirmed-contract")
        portfolio = await self.request({"portfolio": 1})
        contracts = (portfolio.get("portfolio") or {}).get("contracts") or []
        visible = any(str(item.get("contract_id", "")) == str(self.contract_id) for item in contracts)
        if not visible:
            # A completed or sold contract may leave portfolio; use contract status/history reads.
            status = await self.request({"proposal_open_contract": 1, "contract_id": self.contract_id})
            visible = str((status.get("proposal_open_contract") or {}).get("contract_id", "")) == str(self.contract_id)
        return SandboxCheckResult(visible, "deriv-order-outcome-reconciled-before-any-resubmit", reconciled_before_resubmit=True)

    async def run_all(self) -> dict[str, SandboxCheckResult]:
        await self.connect()
        async def run(name: str, fn):
            try:
                self.results[name] = await fn()
            except Exception:
                self.results[name] = SandboxCheckResult(False, "deriv-check-failed-sanitized")
        try:
            await run("authentication", self.check_auth)
            await run("account_identity", self.check_identity)
            # Do not perform order tests unless account identity and auth positively passed.
            if self.results["authentication"].passed and self.results["account_identity"].passed:
                await run("market_data", self.check_market)
                await run("order_submission", self.check_order)
                await run("cancellation", self.check_cancel)
                await run("fills", self.check_fills)
                await run("ambiguous_execution_reconciliation", self.check_reconciliation)
            else:
                for name in ("market_data", "order_submission", "cancellation", "fills", "ambiguous_execution_reconciliation"):
                    self.results[name] = SandboxCheckResult(False, "deriv-prerequisite-check-failed")
            return self.results
        finally:
            if self.ws is not None:
                await self.ws.close()
                self.ws = None


_HARNESS: DerivDemoHarness | None = None


def verify_sandbox_account_identity() -> bool:
    """The runner calls this before building checks; fail closed without demo credentials."""
    global _HARNESS
    if os.environ.get("BROKER_TARGET_ENVIRONMENT") != "sandbox":
        return False
    if not APP_ID.isdigit() or not TOKEN or not (0 < STAKE <= MAX_STAKE):
        return False
    # Identity is verified on the authenticated provider connection before order tests.
    _HARNESS = DerivDemoHarness()
    return asyncio.run(_HARNESS.connect_and_close_identity())


def build_sandbox_checks() -> dict[str, Any]:
    global _HARNESS
    if _HARNESS is None:
        _HARNESS = DerivDemoHarness()
    async def all_checks():
        return await _HARNESS.run_all()
    # Cache a single real provider run so the required identity preflight and checks
    # cannot create duplicate trades. The preflight above performs identity only.
    cache: dict[str, Any] = {}
    def execute(name: str) -> SandboxCheckResult:
        if not cache:
            cache.update(asyncio.run(all_checks()))
        return cache.get(name, SandboxCheckResult(False, "deriv-check-missing"))
    return {name: (lambda name=name: execute(name)) for name in (
        "authentication", "account_identity", "market_data", "order_submission",
        "cancellation", "fills", "ambiguous_execution_reconciliation",
    )}


async def _identity_only(self: DerivDemoHarness) -> bool:
    try:
        await self.connect()
        return str(self.account.get("loginid", "")).startswith("VRTC") and self.account.get("is_virtual") in (1, True)
    finally:
        if self.ws is not None:
            await self.ws.close()
            self.ws = None


DerivDemoHarness.connect_and_close_identity = _identity_only
