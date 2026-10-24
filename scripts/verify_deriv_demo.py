#!/usr/bin/env python3
"""Explicitly opt-in Deriv demo-account smoke verification.

Never runs against an account unless Deriv confirms its login ID is a virtual
account (VRTC prefix and is_virtual flag). The script does not use the app's
stored OAuth credentials and never prints credentials or raw provider payloads.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import uuid

import websockets

APP_ID = os.environ.get("DERIV_APP_ID", "").strip()
TOKEN = os.environ.get("DERIV_DEMO_TOKEN", "").strip()
SYMBOL = os.environ.get("DERIV_DEMO_SYMBOL", "R_100").strip()
STAKE = float(os.environ.get("DERIV_DEMO_STAKE", "1"))
MAX_STAKE = 1.0
TIMEOUT = 12


class VerificationFailure(RuntimeError):
    pass


async def main() -> int:
    if not APP_ID.isdigit() or not TOKEN:
        raise VerificationFailure("DERIV_APP_ID and DERIV_DEMO_TOKEN are required.")
    if not SYMBOL or len(SYMBOL) > 32:
        raise VerificationFailure("DERIV_DEMO_SYMBOL is invalid.")
    if not (0 < STAKE <= MAX_STAKE):
        raise VerificationFailure("Demo stake must be greater than zero and no more than 1 account currency unit.")

    # Use Deriv's documented WebSocket API and authorize with the configured PAT.
    url = "wss://ws.derivws.com/websockets/v3?" + urllib.parse.urlencode({"app_id": APP_ID})
    evidence: dict[str, object] = {"provider": "deriv", "environment": "sandbox", "symbol": SYMBOL}
    async with websockets.connect(url, open_timeout=TIMEOUT, close_timeout=5, ping_interval=20, ping_timeout=10) as ws:
        async def request(payload: dict) -> dict:
            payload = {**payload, "req_id": int(time.time() * 1000) % 2_000_000_000}
            await ws.send(json.dumps(payload))
            deadline = time.monotonic() + TIMEOUT
            while time.monotonic() < deadline:
                msg = json.loads(await asyncio.wait_for(ws.recv(), max(0.1, deadline - time.monotonic())))
                if msg.get("req_id") != payload["req_id"]:
                    continue
                if msg.get("error"):
                    code = (msg["error"] or {}).get("code", "ProviderError")
                    raise VerificationFailure(f"Deriv request failed ({code}); provider message suppressed.")
                return msg
            raise VerificationFailure("Deriv request timed out.")

        auth = await request({"authorize": TOKEN})
        account = auth.get("authorize") or {}
        loginid = str(account.get("loginid") or "")
        is_virtual = account.get("is_virtual")
        if not loginid.startswith("VRTC") or is_virtual not in (1, True):
            raise VerificationFailure("Deriv did not positively verify a virtual/demo account; no trade was submitted.")
        currency = str(account.get("currency") or "")
        evidence["account_identity"] = "verified_virtual_account"
        evidence["authentication"] = "passed"

        tick = await request({"ticks": SYMBOL})
        quote = (tick.get("tick") or {}).get("quote")
        if quote is None:
            raise VerificationFailure("Deriv returned no quote for the configured symbol.")
        evidence["market_data"] = "passed"

        contracts = await request({"contracts_for": SYMBOL, "currency": currency})
        available = (contracts.get("contracts_for") or {}).get("available")
        if not isinstance(available, list) or not available:
            raise VerificationFailure("No available contracts returned for the configured symbol.")
        # This smoke test deliberately does not submit a buy: a market-data-only
        # run cannot honestly certify order submission, fills, close/cancel, or
        # ambiguous-execution reconciliation.
        evidence["contract_discovery"] = "passed"
        evidence["trade_lifecycle"] = "NOT_RUN_requires_separate_reviewed_trade_test"

    print(json.dumps({
        "provider": "deriv",
        "environment": "sandbox",
        "account_identity_verified": True,
        "checks": evidence,
        "passed": True,
        "trade_lifecycle_verified": False,
        "production_enabled": False,
        "note": "Authentication, virtual-account identity, market data and contract discovery only; no order was submitted.",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:
        # Suppress provider exceptions and any potentially sensitive payload.
        message = str(exc) if isinstance(exc, VerificationFailure) else "Unexpected verification failure; details suppressed."
        print(json.dumps({"provider": "deriv", "environment": "sandbox", "passed": False, "error": message, "production_enabled": False}), file=sys.stderr)
        sys.exit(1)
