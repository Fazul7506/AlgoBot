from decimal import Decimal, InvalidOperation
from .exceptions import ValidationError
from .models import MarketSymbol, Tick

class ValidationService:
    def validate_symbol(self, symbol):
        if isinstance(symbol, MarketSymbol): return symbol
        try: return MarketSymbol.objects.get(symbol=symbol, is_active=True)
        except MarketSymbol.DoesNotExist as exc: raise ValidationError(f"Invalid symbol: {symbol}") from exc
    def validate_tick(self, data):
        if not data.get("symbol"): raise ValidationError("Missing symbol")
        if data.get("epoch") is None: raise ValidationError("Missing timestamp")
        symbol = self.validate_symbol(data["symbol"])
        try:
            quote = Decimal(str(data.get("quote")))
            bid = Decimal(str(data.get("bid", quote) if data.get("bid") is not None else quote))
            ask = Decimal(str(data.get("ask", quote) if data.get("ask") is not None else quote))
            volume = Decimal(str(data.get("volume", 0) or 0))
        except (InvalidOperation, TypeError, ValueError) as exc: raise ValidationError("Corrupted tick") from exc
        if quote < 0 or bid < 0 or ask < 0 or volume < 0: raise ValidationError("Negative market values are rejected")
        epoch = int(data["epoch"])
        latest = Tick.objects.filter(symbol=symbol).order_by("-epoch").first()
        if latest and epoch < latest.epoch: raise ValidationError("Out-of-order tick")
        # Duplicate broker quotes are normal. TickService.ingest owns the
        # idempotent write and the database unique constraint arbitrates races.
        return {"symbol": symbol, "quote": quote, "bid": bid, "ask": ask, "epoch": epoch, "volume": volume}
