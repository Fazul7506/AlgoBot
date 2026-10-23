# Official Deriv market SVG source policy

AlgoBot does not draw, synthesize, or store instrument SVG files. The version-controlled JavaScript manifest contains source URL metadata only. Instrument icons are fetched directly from the SVG URLs published on Deriv's official market catalogue pages and hosted on Deriv's Webflow CDN.

The manifest is synchronized with:
- https://ae.deriv.com/markets/derived-indices
- https://ae.deriv.com/markets/cryptocurrencies
- https://ae.deriv.com/markets/forex
- https://ae.deriv.com/markets/commodities
- https://ae.deriv.com/markets/stock-indices

Run python3 scripts/sync_deriv_market_asset_manifest.py to refresh the source URL manifest. The synchronizer excludes Deriv's explicit instruments-placeholder.svg images and any repeated generic stock-index artwork. It never downloads or generates SVG bytes. Registry resolution matches exact symbols/tickers or normalized official display names to the manifest; unmatched instruments get a neutral text fallback, never a fabricated icon.

Deriv's public Active Symbols API is still the source of truth for the currently tradable symbols. The website manifest is a source of available official SVG URLs, not proof that every active symbol has an official SVG. The live coverage audit must be run in an environment with Deriv WebSocket access before claiming 100% active-symbol coverage. Deriv assets remain subject to Deriv's terms and trademark rules.
