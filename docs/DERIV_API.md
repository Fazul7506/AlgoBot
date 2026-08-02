# Deriv API

Deriv integration is isolated in `apps.deriv.adapter.DerivAdapter` and its websocket engine. No other app should construct Deriv websocket payloads or call Deriv directly.
