import logging

from apps.market_data.constants import EVENT_NEW_CANDLE

logger = logging.getLogger(__name__)


class EventBus:
    def publish(self, event, payload):
        logger.info("market_data.event", extra={"event": event, "payload": payload})
        if event == EVENT_NEW_CANDLE and isinstance(payload, dict):
            # The AI model is intentionally triggered only by closed M1 candles;
            # per-tick inference would overload the Python worker and can use an
            # incomplete candle. Dispatch failures are observable but must not
            # make canonical market-data ingestion fail.
            if payload.get("source") == "tick_stream" and payload.get("timeframe") == "1m" and payload.get("symbol") and payload.get("epoch") is not None:
                try:
                    from apps.ai_engine.tasks import process_closed_candle
                    process_closed_candle.apply_async(
                        kwargs={
                            "symbol": str(payload["symbol"]),
                            "timeframe": "1m",
                            "epoch": int(payload["epoch"]),
                        },
                        queue="celery",
                    )
                except Exception:
                    logger.exception(
                        "ai.candle_close_dispatch_failed",
                        extra={"symbol": payload.get("symbol"), "timeframe": payload.get("timeframe"), "epoch": payload.get("epoch")},
                    )
        return {"event": event, "payload": payload}


event_bus = EventBus()
