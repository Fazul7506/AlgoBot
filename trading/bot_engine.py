import asyncio
import json

import websockets
from asgiref.sync import sync_to_async
from django.conf import settings

from trading.models import Tick
from trading.services.risk_service import RiskService
from trading.services.trade_service import TradeService
from trading.strategies.strategy_manager import StrategyManager

DEFAULT_BROKER_WS_URL = getattr(settings, "BROKER_WS_URL", "")
DEFAULT_BROKER_APP_ID = getattr(settings, "BROKER_APP_ID", "")


def build_websocket_url(base_url=DEFAULT_BROKER_WS_URL, app_id=DEFAULT_BROKER_APP_ID):
    if not base_url:
        return ""
    if app_id and "app_id=" not in base_url:
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}app_id={app_id}"
    return base_url


class BrokerBotEngine:
    """Broker-neutral streaming bot engine.

    The engine accepts broker connection details at runtime instead of hardcoding a
    single vendor.  Brokers that support WebSocket authorization and tick streams
    can map their payload shape through ``auth_message`` and ``ticks_message``.
    """

    def __init__(
        self,
        strategy_name="trend",
        balance=1000.0,
        risk_pct=0.01,
        max_daily_loss_pct=0.05,
        max_stake_pct=0.10,
        max_consecutive_losses=3,
        max_drawdown_pct=0.15,
        websocket_url=None,
        auth_message=None,
        ticks_message=None,
        tick_price_path=("tick", "quote"),
        tick_epoch_path=("tick", "epoch"),
    ):
        self.ws = None
        self.websocket_url = websocket_url or build_websocket_url()
        self.auth_message = auth_message or (lambda token: {"authorize": token})
        self.ticks_message = ticks_message or (lambda symbol: {"ticks": symbol, "subscribe": 1})
        self.tick_price_path = tick_price_path
        self.tick_epoch_path = tick_epoch_path
        self.prices = []
        self.strategy_manager = StrategyManager(default=strategy_name)
        self.risk_service = RiskService(
            balance=balance,
            risk_pct=risk_pct,
            max_daily_loss_pct=max_daily_loss_pct,
            max_stake_pct=max_stake_pct,
            max_consecutive_losses=max_consecutive_losses,
            max_drawdown_pct=max_drawdown_pct,
        )
        self.trade_service = TradeService(risk_service=self.risk_service)
        self.access_token = None
        self.user_id = None
        self.running = True
        self.reconnect_delay = 3

    async def connect(self, account_data: dict):
        self.user_id = account_data["user_id"]
        self.access_token = account_data.get("access_token", "")
        self.websocket_url = account_data.get("websocket_url") or self.websocket_url
        if not self.websocket_url:
            raise ValueError("A broker WebSocket URL is required to start the bot engine")
        await self._connect_ws()
        if self.access_token:
            await self.authorize()

    async def _connect_ws(self):
        try:
            self.ws = await websockets.connect(self.websocket_url)
        except Exception as e:
            print(f"[WS CONNECT ERROR] {e}")
            await asyncio.sleep(self.reconnect_delay)
            return await self._connect_ws()

    async def authorize(self):
        await self.ws.send(json.dumps(self.auth_message(self.access_token)))
        response = json.loads(await self.ws.recv())
        print("AUTH RESPONSE:", response)
        if "error" in response:
            raise Exception(f"Auth failed: {response['error']}")
        return response

    async def stream_ticks(self, symbol="R_75"):
        await self.ws.send(json.dumps(self.ticks_message(symbol)))
        while self.running:
            try:
                data = json.loads(await self.ws.recv())
                price = self._nested_value(data, self.tick_price_path)
                if price is None:
                    continue
                epoch = self._nested_value(data, self.tick_epoch_path)
                asyncio.create_task(self._save_tick(symbol, price, epoch))
                self._update_prices(price)
                result = self.strategy_manager.process_tick(symbol, self.prices)
                if result and result.get("signal"):
                    trade = self.trade_service.open_trade(
                        symbol=symbol,
                        signal_direction=result["signal"],
                        entry_price=price,
                        strategy_name=result["strategy"],
                        confidence=result.get("confidence", 55),
                        market_regime=result.get("market_regime"),
                    )
                    print(f"Opened trade {trade.id} {trade.contract_type} @ {price}" if trade else "Trade blocked by risk manager.")
                print("Tick:", price)
            except websockets.ConnectionClosed:
                print("[WS CLOSED] reconnecting...")
                await self._reconnect(symbol)
            except Exception as e:
                print(f"[STREAM ERROR] {e}")

    @staticmethod
    def _nested_value(data, path):
        current = data
        for key in path:
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
        return current

    async def _save_tick(self, symbol, price, epoch):
        await sync_to_async(Tick.objects.create)(symbol=symbol, price=price, epoch=epoch, user_id=self.user_id)

    def _update_prices(self, price):
        self.prices.append(price)
        if len(self.prices) > 100:
            self.prices.pop(0)

    async def _reconnect(self, symbol):
        await asyncio.sleep(self.reconnect_delay)
        await self._connect_ws()
        if self.access_token:
            await self.authorize()
        await self.stream_ticks(symbol)

    def stop(self):
        self.running = False


DerivBotEngine = BrokerBotEngine
