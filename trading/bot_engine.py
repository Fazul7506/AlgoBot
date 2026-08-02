import asyncio
import json
import websockets
from django.conf import settings
from asgiref.sync import sync_to_async

from trading.models import Tick
from trading.strategies.strategy_manager import StrategyManager
from trading.services.risk_service import RiskService
from trading.services.trade_service import TradeService

APP_ID = settings.DERIV_OAUTH_CLIENT_ID
URL = f"wss://ws.binaryws.com/websockets/v3?app_id={APP_ID}"


class DerivBotEngine:

    def __init__(
        self,
        strategy_name='trend',
        balance=1000.0,
        risk_pct=0.01,
        max_daily_loss_pct=0.05,
        max_stake_pct=0.10,
        max_consecutive_losses=3,
        max_drawdown_pct=0.15,
    ):
        self.ws = None
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
        self.reconnect_delay = 3  # seconds


    # --------------------------------------------------
    # CONNECT
    # --------------------------------------------------
    async def connect(self, account_data: dict):

        self.user_id = account_data["user_id"]
        self.access_token = account_data["access_token"]

        await self._connect_ws()
        await self.authorize()


    async def _connect_ws(self):
        try:
            self.ws = await websockets.connect(URL)
        except Exception as e:
            print(f"[WS CONNECT ERROR] {e}")
            await asyncio.sleep(self.reconnect_delay)
            return await self._connect_ws()


    # --------------------------------------------------
    # AUTH
    # --------------------------------------------------
    async def authorize(self):

        await self.ws.send(json.dumps({
            "authorize": self.access_token
        }))

        response = json.loads(await self.ws.recv())

        print("AUTH RESPONSE:", response)

        if "error" in response:
            raise Exception(f"Auth failed: {response['error']}")

        return response


    # --------------------------------------------------
    # STREAM TICKS (CORE ENGINE LOOP)
    # --------------------------------------------------
    async def stream_ticks(self, symbol="R_75"):

        await self.ws.send(json.dumps({
            "ticks": symbol,
            "subscribe": 1
        }))

        while self.running:

            try:
                data = json.loads(await self.ws.recv())

                if "tick" not in data:
                    continue

                tick = data["tick"]
                price = tick["quote"]
                epoch = tick["epoch"]

                # ------------------------------------------
                # NON-BLOCKING DB WRITE (IMPORTANT UPGRADE)
                # ------------------------------------------
                asyncio.create_task(
                    self._save_tick(symbol, price, epoch)
                )

                # local memory buffer (strategy input)
                self._update_prices(price)

                # strategy engine (CPU only)
                result = self.strategy_manager.process_tick(symbol, self.prices)

                if result and result.get("signal"):
                    entry_price = price
                    trade = self.trade_service.open_trade(
                        symbol=symbol,
                        signal_direction=result["signal"],
                        entry_price=entry_price,
                        strategy_name=result["strategy"],
                        confidence=result.get("confidence", 55),
                        market_regime=result.get("market_regime"),
                    )

                    if trade:
                        print(f"Opened trade {trade.id} {trade.contract_type} @ {entry_price}")
                    else:
                        print("Trade blocked by risk manager.")

                print("Tick:", price)

            except websockets.ConnectionClosed:
                print("[WS CLOSED] reconnecting...")
                await self._reconnect(symbol)

            except Exception as e:
                print(f"[STREAM ERROR] {e}")


    # --------------------------------------------------
    # DB LAYER (ISOLATED)
    # --------------------------------------------------
    async def _save_tick(self, symbol, price, epoch):

        await sync_to_async(Tick.objects.create)(
            symbol=symbol,
            price=price,
            epoch=epoch,
            user_id=self.user_id
        )


    # --------------------------------------------------
    # MEMORY BUFFER
    # --------------------------------------------------
    def _update_prices(self, price):

        self.prices.append(price)

        if len(self.prices) > 100:
            self.prices.pop(0)


    # --------------------------------------------------
    # RECONNECT LOGIC
    # --------------------------------------------------
    async def _reconnect(self, symbol):

        await asyncio.sleep(self.reconnect_delay)

        await self._connect_ws()
        await self.authorize()

        await self.stream_ticks(symbol)


    # --------------------------------------------------
    # STOP ENGINE (IMPORTANT FOR MULTI-USER CONTROL)
    # --------------------------------------------------
    def stop(self):

        self.running = False