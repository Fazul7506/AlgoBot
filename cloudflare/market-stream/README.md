# AlgoBot Deriv market stream — standard Worker + Durable Object + Queue

This is a standard Cloudflare Worker using a Durable Object for the persistent outbound Deriv WebSocket and a Queue to buffer ticks before Django ingestion. No Containers are used.

## Required queues
- `algobot-market-ticks`
- `algobot-market-ticks-dlq`

## Required secrets / variables
Set these Worker secrets:
- `MARKET_STREAM_CONTROL_TOKEN`: protects the scheduled coordinator trigger.
- `CLOUDFLARE_MARKET_STREAM_TOKEN`: bearer token sent to Django; must match Render's `CLOUDFLARE_MARKET_STREAM_TOKEN`.

The configured Deriv WebSocket URL follows the current Django public-stream setting. Confirm the provider endpoint and app requirements with a real non-production smoke test before cutting over.

## Cutover safety
Do not stop Render's `run_market_stream` command until all of the following pass:
1. Deploy the Django endpoint and this Worker without stopping the existing stream.
2. Confirm active symbol discovery, WebSocket subscriptions, queue throughput, tick freshness, candle creation, snapshot updates, and Channels fan-out.
3. Verify reconnect behaviour and dead-letter handling.
4. Compare ticks received by both streams and confirm duplicate ingestion is harmless.
5. Only then disable the Render stream process.

## Scope
This migrates market-stream connectivity and buffering, while Django remains the authoritative validation/persistence layer. It does not migrate the Celery Python task execution runtime. The separate background scheduler currently dispatches to Celery, so Celery workers cannot be removed until each Python task is ported and tested.
