from __future__ import annotations

from math import sqrt
from statistics import mean


def _ohlc(candles):
    rows = []
    for c in candles:
        try:
            row = {k: float(c[k]) for k in ("open", "high", "low", "close")}
            row["volume"] = float(c.get("volume", 0) or 0)
            row["epoch"] = int(c.get("epoch", 0) or 0)
            rows.append(row)
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
    gains = []
    losses = []
    for a, b in zip(values[-n - 1:-1], values[-n:]):
        d = b - a
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain, avg_loss = mean(gains), mean(losses)
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def atr(rows, n=14):
    if len(rows) < 2:
        return None
    trs = []
    for prev, cur in zip(rows[-n - 1:-1], rows[-n:]):
        trs.append(max(cur["high"] - cur["low"], abs(cur["high"] - prev["close"]), abs(cur["low"] - prev["close"])))
    return mean(trs) if trs else None


def bollinger(values, n=20, k=2):
    if len(values) < n:
        return None
    window = values[-n:]
    middle = mean(window)
    sd = sqrt(mean((x - middle) ** 2 for x in window))
    return {"middle": middle, "upper": middle + k * sd, "lower": middle - k * sd, "width": (4 * sd / middle * 100) if middle else 0}


def macd(values):
    if len(values) < 26:
        return None
    stream = [ema(values[:i], 12) - ema(values[:i], 26) for i in range(26, len(values) + 1)]
    line = stream[-1]
    signal = ema(stream, 9)
    return {"macd": line, "signal": signal, "histogram": line - signal if signal is not None else None}


def _swing_points(rows, strength=3):
    highs, lows = [], []
    if len(rows) < strength * 2 + 1:
        return highs, lows
    for i in range(strength, len(rows) - strength):
        window = rows[i - strength:i + strength + 1]
        if rows[i]["high"] == max(x["high"] for x in window):
            highs.append({"index": i, "price": rows[i]["high"], "epoch": rows[i]["epoch"]})
        if rows[i]["low"] == min(x["low"] for x in window):
            lows.append({"index": i, "price": rows[i]["low"], "epoch": rows[i]["epoch"]})
    return highs, lows


def pivots(rows, lookback=5):
    highs, lows = _swing_points(rows, lookback)
    return [(x["index"], x["price"]) for x in highs[-8:]], [(x["index"], x["price"]) for x in lows[-8:]]


def market_structure(rows):
    highs, lows = _swing_points(rows, 3)
    labels = []
    if len(highs) >= 2:
        labels.append("HH" if highs[-1]["price"] > highs[-2]["price"] else "LH")
    if len(lows) >= 2:
        labels.append("HL" if lows[-1]["price"] > lows[-2]["price"] else "LL")
    if labels == ["HH", "HL"]:
        trend = "Bullish structure"
    elif labels == ["LH", "LL"]:
        trend = "Bearish structure"
    elif labels:
        trend = "Mixed structure"
    else:
        trend = "Range"
    return {"trend": trend, "labels": labels, "swing_highs": highs[-12:], "swing_lows": lows[-12:]}


def structure_events(rows):
    highs, lows = _swing_points(rows, 3)
    events = []
    if len(highs) >= 2:
        prev, last = highs[-2], highs[-1]
        if last["price"] > prev["price"]:
            events.append({"type": "HH", "index": last["index"], "price": last["price"]})
        else:
            events.append({"type": "LH", "index": last["index"], "price": last["price"]})
    if len(lows) >= 2:
        prev, last = lows[-2], lows[-1]
        if last["price"] > prev["price"]:
            events.append({"type": "HL", "index": last["index"], "price": last["price"]})
        else:
            events.append({"type": "LL", "index": last["index"], "price": last["price"]})
    if not rows:
        return events
    last_close = rows[-1]["close"]
    if highs and last_close > highs[-1]["price"]:
        events.append({"type": "BOS_BULL", "index": len(rows) - 1, "price": last_close})
    if lows and last_close < lows[-1]["price"]:
        events.append({"type": "BOS_BEAR", "index": len(rows) - 1, "price": last_close})
    return events


def fair_value_gaps(rows):
    gaps = []
    for i in range(2, len(rows)):
        a, c = rows[i - 2], rows[i]
        if c["low"] > a["high"]:
            gaps.append({"type": "bullish", "index": i, "low": a["high"], "high": c["low"], "filled": rows[-1]["low"] <= a["high"]})
        elif c["high"] < a["low"]:
            gaps.append({"type": "bearish", "index": i, "low": c["high"], "high": a["low"], "filled": rows[-1]["high"] >= a["low"]})
    return gaps[-20:]


def liquidity_sweeps(rows):
    highs, lows = _swing_points(rows, 3)
    events = []
    for p in highs[-8:]:
        for i in range(p["index"] + 1, min(len(rows), p["index"] + 12)):
            if rows[i]["high"] > p["price"] and rows[i]["close"] < p["price"]:
                events.append({"type": "buy_side_sweep", "index": i, "level": p["price"]})
                break
    for p in lows[-8:]:
        for i in range(p["index"] + 1, min(len(rows), p["index"] + 12)):
            if rows[i]["low"] < p["price"] and rows[i]["close"] > p["price"]:
                events.append({"type": "sell_side_sweep", "index": i, "level": p["price"]})
                break
    return events[-12:]


def supply_demand(rows):
    zones = []
    for i in range(2, len(rows) - 1):
        cur, nxt = rows[i], rows[i + 1]
        body = abs(cur["close"] - cur["open"])
        rng = max(cur["high"] - cur["low"], 1e-12)
        if body / rng < 0.35 and nxt["close"] > cur["high"]:
            zones.append({"type": "demand", "index": i, "low": cur["low"], "high": cur["high"]})
        elif body / rng < 0.35 and nxt["close"] < cur["low"]:
            zones.append({"type": "supply", "index": i, "low": cur["low"], "high": cur["high"]})
    return zones[-12:]


def candlestick_patterns(rows):
    found = []
    if not rows:
        return found
    for i, c in enumerate(rows[-30:], start=max(0, len(rows) - 30)):
        body = abs(c["close"] - c["open"])
        upper = c["high"] - max(c["open"], c["close"])
        lower = min(c["open"], c["close"]) - c["low"]
        rng = max(c["high"] - c["low"], 1e-12)
        if body / rng < 0.1:
            found.append({"type": "doji", "index": i, "bias": "neutral"})
        elif lower > body * 2 and upper < body:
            found.append({"type": "hammer", "index": i, "bias": "bullish"})
        elif upper > body * 2 and lower < body:
            found.append({"type": "shooting_star", "index": i, "bias": "bearish"})
        if i > 0:
            p = rows[i - 1]
            if p["close"] < p["open"] and c["close"] > c["open"] and c["close"] >= p["open"] and c["open"] <= p["close"]:
                found.append({"type": "bullish_engulfing", "index": i, "bias": "bullish"})
            elif p["close"] > p["open"] and c["close"] < c["open"] and c["open"] >= p["close"] and c["close"] <= p["open"]:
                found.append({"type": "bearish_engulfing", "index": i, "bias": "bearish"})
    return found[-20:]


def fibonacci(rows):
    highs, lows = _swing_points(rows, 3)
    if not highs or not lows:
        return None
    high, low = highs[-1]["price"], lows[-1]["price"]
    if high == low:
        return None
    diff = high - low
    return {str(r): high - diff * r for r in (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)}


def volatility_regime(rows, atr_value=None):
    if len(rows) < 30:
        return "unknown"
    atr_value = atr_value or atr(rows)
    ranges = [x["high"] - x["low"] for x in rows[-20:]]
    avg_range = mean(ranges) if ranges else 0
    if not avg_range:
        return "unknown"
    ratio = (atr_value or avg_range) / avg_range
    if ratio > 1.35:
        return "expanding"
    if ratio < 0.75:
        return "contracting"
    return "normal"


def analyze_candles(candles, symbol="", timeframe=""):
    rows = _ohlc(candles)
    if not rows:
        return {"symbol": symbol, "timeframe": timeframe, "status": "no_data", "candles": 0}

    closes = [x["close"] for x in rows]
    price = closes[-1]
    s20, s50, s200 = sma(closes, 20), sma(closes, 50), sma(closes, 200)
    e9, e21 = ema(closes, 9), ema(closes, 21)
    r, a, bb, m = rsi(closes), atr(rows), bollinger(closes), macd(closes)
    structure = market_structure(rows)
    events = structure_events(rows)
    fvgs = fair_value_gaps(rows)
    sweeps = liquidity_sweeps(rows)
    zones = supply_demand(rows)
    patterns = candlestick_patterns(rows)

    score = 50.0
    factors = []
    if e9 is not None and e21 is not None:
        score += 10 if e9 > e21 else -10
        factors.append("EMA 9/21 trend")
    if s50 is not None:
        score += 8 if price > s50 else -8
        factors.append("SMA 50 location")
    if s200 is not None:
        score += 8 if price > s200 else -8
        factors.append("SMA 200 regime")
    if r is not None:
        if r < 30:
            score += 8
            factors.append("RSI oversold")
        elif r > 70:
            score -= 8
            factors.append("RSI overbought")
    if m and m["histogram"] is not None:
        score += 7 if m["histogram"] > 0 else -7
        factors.append("MACD momentum")
    if structure["trend"] == "Bullish structure":
        score += 7
        factors.append("Bullish market structure")
    elif structure["trend"] == "Bearish structure":
        score -= 7
        factors.append("Bearish market structure")
    recent_pattern = patterns[-1] if patterns else None
    if recent_pattern and recent_pattern["bias"] != "neutral":
        score += 4 if recent_pattern["bias"] == "bullish" else -4
        factors.append(recent_pattern["type"].replace("_", " ").title())
    if sweeps:
        sweep = sweeps[-1]
        score += 4 if sweep["type"] == "sell_side_sweep" else -4
        factors.append(sweep["type"].replace("_", " ").title())

    score = max(0, min(100, score))
    label = "Strong Bullish" if score >= 75 else "Bullish" if score >= 60 else "Neutral" if score > 40 else "Bearish" if score > 25 else "Strong Bearish"
    highs, lows = pivots(rows)
    resistance = max((v for _, v in highs), default=max(x["high"] for x in rows[-20:]))
    support = min((v for _, v in lows), default=min(x["low"] for x in rows[-20:]))
    fib = fibonacci(rows)

    return {
        "symbol": symbol, "timeframe": timeframe, "status": "ok", "candles": len(rows), "price": price,
        "change_pct": ((price / closes[0]) - 1) * 100 if closes[0] else 0,
        "signal": label, "score": round(score, 2),
        "confidence": round(min(99, 50 + abs(score - 50) * 0.9), 2),
        "indicators": {"sma20": s20, "sma50": s50, "sma200": s200, "ema9": e9, "ema21": e21, "rsi14": r, "atr14": a, "bollinger": bb, "macd": m},
        "levels": {"support": support, "resistance": resistance, "range": resistance - support},
        "structure": structure["trend"],
        "market_structure": structure,
        "events": events,
        "fair_value_gaps": fvgs,
        "liquidity_sweeps": sweeps,
        "supply_demand": zones,
        "candlestick_patterns": patterns,
        "fibonacci": fib,
        "volatility_regime": volatility_regime(rows, a),
        "factors": factors,
        "last_candles": rows[-300:],
    }
