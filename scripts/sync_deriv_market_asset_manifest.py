#!/usr/bin/env python3
"""Sync official Deriv SVG source URLs without downloading or generating SVG files.

Scrapes Deriv's official market catalogues, including individual stocks (not only
stock indices), and preserves verified modern media-CDN synthetic assets.
"""
import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "static/js/deriv_market_asset_manifest.js"
PAGES = [
    ("synthetic-indices", "derived-indices"),
    ("synthetic-indices", "derived-indices/synthetic-indices"),
    ("cryptocurrency", "cryptocurrencies"),
    ("forex", "forex"),
    ("commodities", "commodities"),
    ("stocks-and-indices", "stock-indices"),
    ("stocks-and-indices", "stocks"),
]
BASE = "https://ae.deriv.com/markets/"
USER_AGENT = "AlgoBot-Deriv-Asset-Sync/1.0"
OFFICIAL_WEBFLOW_PREFIX = "https://cdn.prod.website-files.com/"
OFFICIAL_DERIV_MEDIA_PREFIX = "https://media.ffycdn.net/eu/deriv/"
OFFICIAL_SMARTCHARTS_RAW_PREFIX = "https://raw.githubusercontent.com/deriv-com/deriv-smartcharts/e8243d9cb0f47a3d3dcbd184910d36667eb4b43d/"
OFFICIAL_SMARTCHARTS_SOURCE_PREFIX = "https://github.com/deriv-com/deriv-smartcharts/blob/e8243d9cb0f47a3d3dcbd184910d36667eb4b43d/"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", "replace")


def normalise_name(name):
    return re.sub(r"[^A-Z0-9]", "", name.upper())


def validate_svg_asset(url):
    """Fetch an official catalogue asset and reject HTML/error pages masquerading as SVG."""
    if not (
        url.startswith(OFFICIAL_WEBFLOW_PREFIX)
        or url.startswith(OFFICIAL_DERIV_MEDIA_PREFIX)
        or url.startswith(OFFICIAL_SMARTCHARTS_RAW_PREFIX)
    ) or not url.lower().endswith(".svg"):
        raise ValueError("Unapproved official SVG URL: " + url)
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "image/svg+xml"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        content_type = response.headers.get("Content-Type", "").lower()
        sample = response.read(16384).decode("utf-8", "replace").lstrip("\ufeff\x00 \t\r\n")
    if "text/html" in content_type or not re.search(r"<svg(?:\s|>)", sample, re.I):
        raise ValueError("Official asset did not return SVG markup: " + url)


def load_existing_official_media_entries():
    """Retain verified modern synthetic SVG URLs not emitted by the legacy scraper."""
    if not OUTPUT.exists():
        return []
    text = OUTPUT.read_text(encoding="utf-8")
    match = re.search(r"Object\.freeze\((\{.*\})\);", text, re.S)
    if not match:
        return []
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    preserved = []
    for item in payload.get("entries", []):
        url = item.get("url", "")
        if (
            item.get("market") in {"synthetic-indices", "basket-indices", "stocks-and-indices"}
            and (
                url.startswith(OFFICIAL_DERIV_MEDIA_PREFIX)
                or url.startswith(OFFICIAL_SMARTCHARTS_RAW_PREFIX)
            )
            and url.lower().endswith(".svg")
            and "instruments-placeholder.svg" not in url
            and item.get("name")
            and (
                item.get("sourcePage", "").startswith(("https://deriv.com/", "https://ae.deriv.com/"))
                or item.get("sourcePage", "").startswith(OFFICIAL_SMARTCHARTS_SOURCE_PREFIX)
            )
        ):
            preserved.append(item)
    return preserved


def collect(market, slug):
    url = urllib.parse.urljoin(BASE, slug)
    seen_urls = set()
    entries = {}
    while url and url not in seen_urls and len(seen_urls) < 60:
        seen_urls.add(url)
        page = fetch(url)
        rows = re.findall(
            r'<img[^>]*src="([^"]+)"[^>]*class="ts_cell-icon"[^>]*>\s*'
            r'<p[^>]*fs-cmsfilter-field="name"[^>]*>(.*?)</p>',
            page, re.S
        )
        for asset_url, raw_name in rows:
            label = html.unescape(re.sub(r"<[^>]+>", "", raw_name)).strip()
            asset_url = html.unescape(asset_url)
            if not label or "instruments-placeholder.svg" in asset_url:
                continue
            allowed_source = asset_url.startswith(OFFICIAL_WEBFLOW_PREFIX) or (
                market in {"synthetic-indices", "stocks-and-indices"}
                and asset_url.startswith(OFFICIAL_DERIV_MEDIA_PREFIX)
            )
            if not allowed_source or not asset_url.lower().endswith(".svg"):
                continue
            symbol = None
            name = label
            if market == "stocks-and-indices":
                # Stock catalogue labels have the form "AAPL.OQ: Apple Inc (NASDAQ)".
                match = re.match(r"^([A-Z0-9.^_-]+):\s*(.+)$", label)
                if match:
                    symbol, name = match.group(1).strip(), match.group(2).strip()
            key = normalise_name(symbol or name)
            entry = {
                "market": market,
                "name": name,
                "url": asset_url,
                "sourcePage": BASE + slug,
            }
            if symbol:
                entry["symbol"] = symbol
            entries[key] = entry
        match = re.search(r'<a[^>]*href="([^"]+)"[^>]*aria-label="Next Page"', page)
        url = urllib.parse.urljoin(url, match.group(1)) if match else None
    return list(entries.values())


def main():
    entries_by_name = {
        normalise_name(item.get("symbol") or item["name"]): item
        for item in load_existing_official_media_entries()
    }
    legacy_synthetic_by_name = {}
    for market, slug in PAGES:
        collected = collect(market, slug)
        if market == "synthetic-indices" and slug == "derived-indices":
            legacy_synthetic_by_name.update({
                normalise_name(item.get("symbol") or item["name"]): item
                for item in collected
            })
        for item in collected:
            key = normalise_name(item.get("symbol") or item["name"])
            # The modern catalogue is preferred only when it identifies an asset
            # uniquely. Keep legacy candidates available as a verified fallback.
            modern_synthetic_catalogue = (
                market == "synthetic-indices"
                and slug == "derived-indices/synthetic-indices"
            )
            if key not in entries_by_name or modern_synthetic_catalogue or (
                market != "synthetic-indices"
                and entries_by_name[key].get("market") != "synthetic-indices"
            ):
                entries_by_name[key] = item

    # Preserve Deriv's catalogue mapping exactly, including shared official SVG
    # URLs assigned to multiple instruments. The registry resolves by exact name or
    # symbol, so shared URLs do not cause cross-instrument fuzzy matches.
    entries = list(entries_by_name.values())
    entries.sort(key=lambda item: (item["market"], item["name"]))
    for asset_url in sorted({item["url"] for item in entries}):
        validate_svg_asset(asset_url)

    payload = {"source": "Official Deriv market catalogue pages", "entries": entries}
    OUTPUT.write_text(
        "/* Source URL metadata only. No SVG bytes are generated or stored by AlgoBot. */\n"
        "window.AlgoBotDerivMarketAssetManifest = Object.freeze(" +
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ");\n",
        encoding="utf-8",
    )
    print("Wrote", len(entries), "verified Deriv-hosted SVG URL records to", OUTPUT)


if __name__ == "__main__":
    main()
