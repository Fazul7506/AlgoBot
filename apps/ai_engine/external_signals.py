"""Persisted, timestamped external sentiment and Level-2 order-book signals.

RSS and order-book providers are configurable. No synthetic sentiment or
candle-volume proxy is generated when an external source is unavailable.
"""
from __future__ import annotations

import email.utils
import hashlib
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from bisect import bisect_right
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import requests
from django.utils import timezone as django_timezone

from .models import OrderBookSnapshot, SentimentObservation

logger = logging.getLogger(__name__)
TOKEN_RE = re.compile(r"[^A-Z0-9]+")


def _utc_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _feed_items(payload: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(payload)
    items = []
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1].lower()
        if tag not in {"item", "entry"}:
            continue
        values = {}
        for child in list(node):
            key = child.tag.rsplit("}", 1)[-1].lower()
            if key == "link":
                value = child.attrib.get("href") or child.text or ""
            else:
                value = "".join(child.itertext())
            values[key] = value.strip()
        title = values.get("title", "")
        summary = values.get("description") or values.get("summary") or values.get("content", "")
        published = values.get("pubdate") or values.get("published") or values.get("updated")
        items.append({"title": title, "summary": summary, "link": values.get("link", ""), "published": published or ""})
    return items


def ingest_rss_sentiment() -> dict[str, int]:
    """Fetch configured public RSS feeds and persist only explicitly mapped assets."""
    feed_urls = [item.strip() for item in os.environ.get("AI_SENTIMENT_RSS_URLS", "").split(",") if item.strip()]
    try:
        symbol_keywords = json.loads(os.environ.get("AI_SENTIMENT_SYMBOL_KEYWORDS_JSON", "{}"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("AI_SENTIMENT_SYMBOL_KEYWORDS_JSON must be valid JSON") from exc
    if not isinstance(symbol_keywords, dict):
        raise RuntimeError("AI_SENTIMENT_SYMBOL_KEYWORDS_JSON must be a JSON object")
    if not feed_urls or not symbol_keywords:
        return {"feeds": 0, "items": 0, "observations": 0, "configured": 0}

    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    analyzer = SentimentIntensityAnalyzer()
    item_count = observation_count = 0
    for feed_url in feed_urls:
        parsed = urlparse(feed_url)
        if parsed.scheme != "https" or not parsed.netloc:
            logger.warning("Skipping non-HTTPS sentiment feed URL")
            continue
        try:
            response = requests.get(feed_url, timeout=(4, 12), headers={"User-Agent": "AlgoBotMarketResearch/1.0"})
            response.raise_for_status()
            items = _feed_items(response.content)
        except (requests.RequestException, ET.ParseError, ValueError) as exc:
            logger.warning("Sentiment RSS fetch failed: %s", str(exc)[:200])
            continue
        for item in items:
            published_at = _utc_datetime(item["published"])
            if published_at is None or published_at > django_timezone.now() + timedelta(minutes=5):
                continue
            text = f'{item["title"]} {item["summary"]}'.strip()
            if len(text) < 20:
                continue
            item_count += 1
            normalized = text.upper()
            score = analyzer.polarity_scores(text)
            digest = hashlib.sha256((feed_url + "|" + item["link"] + "|" + text).encode()).hexdigest()
            for symbol, keywords in symbol_keywords.items():
                if not isinstance(keywords, list) or not keywords:
                    continue
                if not any(str(word).strip() and str(word).upper() in normalized for word in keywords):
                    continue
                _, created = SentimentObservation.objects.get_or_create(
                    content_hash=digest,
                    symbol=str(symbol).upper(),
                    defaults={
                        "source": feed_url,
                        "source_url": item["link"][:1000],
                        "published_at": published_at,
                        "compound": float(score["compound"]),
                        "positive": float(score["pos"]),
                        "neutral": float(score["neu"]),
                        "negative": float(score["neg"]),
                    },
                )
                observation_count += int(created)
    return {"feeds": len(feed_urls), "items": item_count, "observations": observation_count, "configured": len(symbol_keywords)}


def normalize_orderbook(payload: dict[str, Any]) -> dict[str, float]:
    """Validate provider-neutral Level-2 payload: bids/asks are [price, quantity] pairs."""
    bids, asks = payload.get("bids"), payload.get("asks")
    if not isinstance(bids, list) or not isinstance(asks, list) or not bids or not asks:
        raise ValueError("Order-book provider must return non-empty bids and asks arrays")
    def depth(levels):
        total = 0.0
        for level in levels[:10]:
            if not isinstance(level, (list, tuple)) or len(level) < 2:
                raise ValueError("Invalid order-book level")
            price, quantity = float(level[0]), float(level[1])
            if price <= 0 or quantity < 0:
                raise ValueError("Order-book prices must be positive and quantities non-negative")
            total += quantity
        return total
    bid_volume, ask_volume = depth(bids), depth(asks)
    denominator = bid_volume + ask_volume
    if denominator <= 0:
        raise ValueError("Order-book top-level depth is empty")
    best_bid = max(float(level[0]) for level in bids[:10])
    best_ask = min(float(level[0]) for level in asks[:10])
    if best_ask < best_bid:
        raise ValueError("Order-book is crossed and cannot be trusted")
    mid = (best_bid + best_ask) / 2.0
    return {
        "bid_volume": bid_volume,
        "ask_volume": ask_volume,
        "imbalance": (bid_volume - ask_volume) / denominator,
        "spread_bps": ((best_ask - best_bid) / mid) * 10000.0 if mid else 0.0,
    }


def ingest_orderbook_snapshots() -> dict[str, int]:
    """Poll a configured Level-2 provider; no candle-volume fallback is allowed."""
    endpoint = os.environ.get("ORDER_BOOK_API_URL", "").strip()
    if not endpoint:
        return {"symbols": 0, "snapshots": 0, "configured": 0}
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc or "{symbol}" not in endpoint:
        raise RuntimeError("ORDER_BOOK_API_URL must be HTTPS and contain a {symbol} placeholder")
    token = os.environ.get("ORDER_BOOK_API_TOKEN", "").strip()
    from apps.market_data.services import MarketDataService
    configured_symbols = [item.strip() for item in os.environ.get("ORDER_BOOK_SYMBOLS", "").split(",") if item.strip()]
    symbols_to_poll = configured_symbols or list(
        MarketDataService.symbols.catalogue(active=True, tradable=True).values_list("symbol", flat=True)
    )
    count = symbols = 0
    for symbol in symbols_to_poll:
        symbols += 1
        try:
            response = requests.get(
                endpoint.replace("{symbol}", requests.utils.quote(str(symbol), safe="")),
                headers={"Authorization": f"Bearer {token}"} if token else {},
                timeout=(4, 10),
            )
            response.raise_for_status()
            book = normalize_orderbook(response.json())
            OrderBookSnapshot.objects.create(symbol=str(symbol), observed_at=django_timezone.now(), **book)
            count += 1
        except (requests.RequestException, ValueError, TypeError) as exc:
            logger.warning("Order-book snapshot unavailable symbol=%s reason=%s", symbol, str(exc)[:200])
    return {"symbols": symbols, "snapshots": count, "configured": 1}


def _sentiment_asof(symbol: str, epoch: int) -> tuple[float, float, float, float, float]:
    cutoff = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    recent = list(SentimentObservation.objects.filter(
        symbol=symbol, published_at__lte=cutoff, published_at__gte=cutoff - timedelta(hours=24)
    ).order_by("-published_at")[:100].values_list("compound", "positive", "negative", "published_at"))
    if not recent:
        return 0.0, 0.0, 0.0, 1440.0, 0.0
    scores = [float(row[0]) for row in recent]
    age = max(0.0, (cutoff - recent[0][3]).total_seconds() / 60.0)
    return sum(scores) / len(scores), sum(float(r[1]) for r in recent) / len(recent), sum(float(r[2]) for r in recent) / len(recent), age, 1.0


def _orderbook_asof(symbol: str, epoch: int) -> tuple[float, float, float, float]:
    cutoff = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    row = OrderBookSnapshot.objects.filter(symbol=symbol, observed_at__lte=cutoff).order_by("-observed_at").first()
    if row is None or (cutoff - row.observed_at).total_seconds() > 300:
        return 0.0, 0.0, 0.0, 0.0
    return float(row.imbalance), float(row.bid_volume + row.ask_volume), float(row.spread_bps), 1.0


def current_external_signal_features(symbol: str, before_epoch: int | None = None) -> dict[str, float]:
    epoch = int(before_epoch) if before_epoch is not None else int(django_timezone.now().timestamp())
    sentiment, positive, negative, age, sentiment_available = _sentiment_asof(symbol, epoch)
    imbalance, depth, spread_bps, book_available = _orderbook_asof(symbol, epoch)
    return {
        "sentiment_compound": sentiment,
        "sentiment_positive": positive,
        "sentiment_negative": negative,
        "sentiment_age_minutes": age,
        "sentiment_available": sentiment_available,
        "orderbook_imbalance": imbalance,
        "orderbook_total_depth": depth,
        "orderbook_spread_bps": spread_bps,
        "orderbook_available": book_available,
    }


class ExternalSignalTimeline:
    """Preload external observations once per training dataset, then do as-of joins."""
    def __init__(self, symbol: str, first_epoch: int, last_epoch: int):
        first = datetime.fromtimestamp(int(first_epoch), tz=timezone.utc)
        last = datetime.fromtimestamp(int(last_epoch), tz=timezone.utc)
        sentiment_rows = SentimentObservation.objects.filter(
            symbol=symbol,
            published_at__gte=first - timedelta(hours=24),
            published_at__lte=last,
        ).order_by("published_at").values_list(
            "compound", "positive", "negative", "published_at"
        )
        self.sentiment = list(sentiment_rows)
        self.sentiment_times = [row[3].timestamp() for row in self.sentiment]
        book_rows = OrderBookSnapshot.objects.filter(
            symbol=symbol,
            observed_at__gte=first - timedelta(minutes=5),
            observed_at__lte=last,
        ).order_by("observed_at").values_list(
            "imbalance", "bid_volume", "ask_volume", "spread_bps", "observed_at"
        )
        self.books = list(book_rows)
        self.book_times = [row[4].timestamp() for row in self.books]

    def features(self, epoch: int) -> dict[str, float]:
        cutoff = float(epoch)
        sentiment_end = bisect_right(self.sentiment_times, cutoff)
        sentiment_start = bisect_right(self.sentiment_times, cutoff - 86400)
        recent = self.sentiment[max(sentiment_start, sentiment_end - 100):sentiment_end]
        if recent:
            count = len(recent)
            sentiment = sum(float(row[0]) for row in recent) / count
            positive = sum(float(row[1]) for row in recent) / count
            negative = sum(float(row[2]) for row in recent) / count
            age = max(0.0, (cutoff - self.sentiment_times[sentiment_end - 1]) / 60.0)
            sentiment_available = 1.0
        else:
            sentiment = positive = negative = 0.0
            age = 1440.0
            sentiment_available = 0.0

        book_end = bisect_right(self.book_times, cutoff)
        book = self.books[book_end - 1] if book_end else None
        if book and cutoff - self.book_times[book_end - 1] <= 300:
            imbalance = float(book[0])
            depth = float(book[1]) + float(book[2])
            spread_bps = float(book[3])
            book_available = 1.0
        else:
            imbalance = depth = spread_bps = 0.0
            book_available = 0.0
        return {
            "sentiment_compound": sentiment,
            "sentiment_positive": positive,
            "sentiment_negative": negative,
            "sentiment_age_minutes": age,
            "sentiment_available": sentiment_available,
            "orderbook_imbalance": imbalance,
            "orderbook_total_depth": depth,
            "orderbook_spread_bps": spread_bps,
            "orderbook_available": book_available,
        }
