#!/usr/bin/env python3
"""Sync source URLs for official Deriv market SVGs; never downloads or generates SVG files."""
import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "static/js/deriv_market_asset_manifest.js"
PAGES = {
    "synthetic-indices": "derived-indices",
    "cryptocurrency": "cryptocurrencies",
    "forex": "forex",
    "commodities": "commodities",
    "stocks-and-indices": "stock-indices",
}
BASE = "https://ae.deriv.com/markets/"
USER_AGENT = "AlgoBot-Deriv-Asset-Sync/1.0"

def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", "replace")

def collect(market, slug):
    url = urllib.parse.urljoin(BASE, slug)
    seen_urls = set()
    entries = {}
    while url and url not in seen_urls and len(seen_urls) < 30:
        seen_urls.add(url)
        page = fetch(url)
        rows = re.findall(
            r'<img[^>]*src="([^"]+)"[^>]*class="ts_cell-icon"[^>]*>\s*'
            r'<p[^>]*fs-cmsfilter-field="name"[^>]*>(.*?)</p>',
            page, re.S
        )
        for asset_url, raw_name in rows:
            name = html.unescape(re.sub(r"<[^>]+>", "", raw_name)).strip()
            asset_url = html.unescape(asset_url)
            if not name or "instruments-placeholder.svg" in asset_url:
                continue
            if not asset_url.startswith("https://cdn.prod.website-files.com/") or not asset_url.lower().endswith(".svg"):
                continue
            # ETFs reuse the same US-500 artwork for unrelated products, so do not include those.
            if market == "stocks-and-indices" and slug == "stock-indices":
                pass
            key = re.sub(r"[^A-Z0-9]", "", name.upper())
            entries[key] = {
                "market": market,
                "name": name,
                "url": asset_url,
                "sourcePage": BASE + slug,
            }
        match = re.search(r'<a[^>]*href="([^"]+)"[^>]*aria-label="Next Page"', page)
        url = urllib.parse.urljoin(url, match.group(1)) if match else None
    return list(entries.values())

def main():
    entries = []
    for market, slug in PAGES.items():
        entries.extend(collect(market, slug))
    # Reject duplicate asset URLs that are reused across distinct instrument labels.
    counts = {}
    for item in entries:
        counts[item["url"]] = counts.get(item["url"], 0) + 1
    entries = [
        item for item in entries
        if not (item["market"] == "stocks-and-indices" and counts[item["url"]] > 1)
    ]
    entries.sort(key=lambda item: (item["market"], item["name"]))
    payload = {
        "source": "Official Deriv market catalogue pages",
        "generatedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "entries": entries,
    }
    OUTPUT.write_text(
        "/* Source URL metadata only. No SVG bytes are generated or stored by AlgoBot. */\n"
        "window.AlgoBotDerivMarketAssetManifest = Object.freeze(" +
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ");\n",
        encoding="utf-8",
    )
    print("Wrote", len(entries), "verified Deriv-hosted SVG URL records to", OUTPUT)

if __name__ == "__main__":
    main()
