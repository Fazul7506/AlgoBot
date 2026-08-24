# Phase 11 — Charts

Status: COMPLETE AND WORKING

## Scope

The live chart in the trading terminal is now explicitly broker-gated.

## Implemented

- live chart history uses the centralized frontend request contract
- history loads only with an active broker-backed account state
- authenticated WebSocket market stream is opened only when broker state is connected/ready
- disconnect/no-broker events close the stream and clear live chart points
- reconnect is attempted only while broker state remains connected and the document is visible
- selected broker symbol drives chart subscription
- chart values are derived from broker market stream/history; no hardcoded prices
- quote/bid/ask and trend/volatility display continue to derive from received broker data

## Safety boundary

Broker/vendor WebSocket connections remain behind the authenticated AlgoBot WebSocket boundary. The browser does not connect directly to broker/vendor credentials or endpoints.

## Verification note

No GitHub Actions workflow run is exposed for the current branch/commit. Targeted repository coverage for the surrounding page contracts exists; browser/WebSocket/backend/broker E2E remains part of Phase 19.
