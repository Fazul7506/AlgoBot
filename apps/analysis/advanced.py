from __future__ import annotations

from math import sqrt
from statistics import mean


def _ohlc(candles):
    rows = []
    for c in candles:
        try:
            o, h, l, cl = (float(c[k]) for k in ("open", "high", "low", "close"))
            rows.append({"open": o, "high": h, "low": l, "close": cl, "volume": float(c.get("volume", 0) or 0), "epoch": int(c.get("epoch", 0) or 0)})
        except (KeyError, TypeError, ValueError):
            continue
    return rows


def sma(values, n):
    return mean(values[-n:]) if len(values) >= n else None


def ema(values, n):
    if not values:
        return None
    n = min(n, len(values))
    value = mean(values[:n])
    alpha = 2 / (n + 1)
    for x in values[n:]:
        value = alpha * x + (1 - alpha) * value
    return value


def rsi(values, n=14):
    if len(values) <= n:
        return None
    gains, losses = [], []
    for a, b in zip(values[-n-1:-1], values[-n:]):
        d = b - a
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    avg_gain, avg_loss = mean(gains), mean(losses)
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def atr(rows, n=14):
    if len(rows) < 2:
        return None
    trs = []
    for prev, cur in zip(rows[-n-1:-1], rows[-n:]):
        trs.append(max(cur["high"] - cur["low"], abs(cur["high"] - prev["close"]), abs(cur["low"] - prev["close"])))
    return mean(trs) if trs else None


def bollinger(values, n=20, k=2):
    if len(values) < n:
        return None
    window = values[-n:]; m = mean(window)
    sd = sqrt(mean((x - m) ** 2 for x in window))
    return {"middle": m, "upper": m + k * sd, "lower": m - k * sd, "width": (4 * sd / m * 100) if m else 0}


def macd(values):
    if len(values) < 26:
        return None
    line = ema(values, 12) - ema(values, 26)
    # Signal is approximated from the current MACD stream when historical MACD values are unavailable.
    signal = ema([ema(values[:i], 12) - ema(values[:i], 26) for i in range(26, len(values) + 1)], 9)
    return {"macd": line, "signal": signal, "histogram": line - signal if signal is not None else None}


def pivots(rows, lookback=5):
    highs, lows = [], []
    for i in range(lookback, len(rows) - lookback):
        h, l = rows[i]["high"], rows[i]["low"]
        if h == max(x["high"] for x in rows[i-lookback:i+lookback+1]): highs.append((i, h))
        if l == min(x["low"] for x in rows[i-lookback:i+lookback+1]): lows.append((i, l))
    return highs[-8:], lows[-8:]


def analyze_candles(candles, symbol="", timeframe=""):
    rows = _ohlc(candles)
    if not rows:
        return {"symbol": symbol, "timeframe": timeframe, "status": "no_data", "candles": 0}
    closes = [x["close"] for x in rows]; price = closes[-1]
    s20, s50, s200 = sma(closes, 20), sma(closes, 50), sma(closes, 200)
    e9, e21 = ema(closes, 9), ema(closes, 21)
    r = rsi(closes); a = atr(rows); bb = bollinger(closes); m = macd(closes)
    score = 50.0
    factors = []
    if e9 and e21: score += 10 if e9 > e21 else -10; factors.append("EMA9/EMA21")
    if s50: score += 10 if price > s50 else -10; factors.append("SMA50")
    if s200: score += 10 if price > s200 else -10; factors.append("SMA200")
    if r is not None: score += 8 if r < 30 else (-8 if r > 70 else 0); factors.append("RSI14")
    if m and m["histogram"] is not None: score += 7 if m["histogram"] > 0 else -7; factors.append("MACD")
    score = max(0, min(100, score))
    label = "Strong Bullish" if score >= 75 else "Bullish" if score >= 60 else "Neutral" if score > 40 else "Bearish" if score > 25 else "Strong Bearish"
    highs, lows = pivots(rows)
    resistance = max((v for _, v in highs), default=max(x["high"] for x in rows[-20:]))
    support = min((v for _, v in lows), default=min(x["low"] for x in rows[-20:]))
    structure = "Range"
    if len(highs) >= 2 and len(lows) >= 2:
        structure = "Bullish structure" if highs[-1][1] > highs[-2][1] and lows[-1][1] > lows[-2][1] else "Bearish structure" if highs[-1][1] < highs[-2][1] and lows[-1][1] < lows[-2][1] else "Mixed structure"
    return {
        "symbol": symbol, "timeframe": timeframe, "status": "ok", "candles": len(rows), "price": price,
        "change_pct": ((price / closes[0]) - 1) * 100 if closes[0] else 0,
        "signal": label, "score": round(score, 2), "confidence": round(min(99, 50 + abs(score - 50) * 0.9), 2),
        "indicators": {"sma20": s20, "sma50": s50, "sma200": s200, "ema9": e9, "ema21": e21, "rsi14": r, "atr14": a, "bollinger": bb, "macd": m},
        "levels": {"support": support, "resistance": resistance, "range": resistance - support},
        "structure": structure, "factors": factors,
        "last_candles": rows[-200:],
    }
