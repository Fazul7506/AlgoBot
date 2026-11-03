# AlgoBot Deriv market stream — standard Worker + Durable Object + Queue

This is a standard Cloudflare Worker using a Durable Object for the persistent outbound Deriv WebSocket and a Queue to buffer ticks before Django ingestion. No Containers are used.

## Required queues
- `algobot-market-ticks`
- `algobot-market-ticks-dlq`

## Required secrets / variables
Set these Worker secrets:
- `MARKET_STREAM_CONTROL_TOKEN`: protects the scheduled coordinator trigger.
- `CLOUDFLARE_MARKET_STREAM_TOKEN`: bearer token sent to Django; must match Render's `CLOUDFLARE_MARKET_STREAM_TOKEN`.

The public market-data URL is `wss://api.derivws.com/trading/v1/options/ws/public`. This is Deriv's unauthenticated Options API public endpoint. The stream subscribes with `{ "ticks": [<symbols>], "subscribe": 1, "req_id": 1 }`; Deriv documents `ticks` as accepting a symbol or an array of symbols. See the [official public endpoint](https://developers.deriv.com/docs/options/ws-public/) and [tick stream request schema](https://developers.deriv.com/docs/data/ticks/).

Required variables:
- `DERIV_PUBLIC_WS_URL`: the public URL above.
- `ALGOBOT_MARKET_SYMBOLS_URL`: Django's authenticated active-symbol endpoint.
- `ALGOBOT_MARKET_TICK_URL`: Django's authenticated tick ingestion endpoint.
- `CLOUDFLARE_MARKET_STREAM_ACTIVE`: keep `false` until cutover.
- `MARKET_STREAM_CONTROL_TOKEN`: Worker-only secret used to protect the Durable Object control request.
- `CLOUDFLARE_MARKET_STREAM_TOKEN`: Worker secret matching Django's Render environment variable.

Set secrets with Wrangler from this directory (enter values interactively; never commit them):
```sh
npx wrangler secret put MARKET_STREAM_CONTROL_TOKEN
npx wrangler secret put CLOUDFLARE_MARKET_STREAM_TOKEN
```


## Activation gate
The Worker defaults to disabled (`CLOUDFLARE_MARKET_STREAM_ACTIVE=false`). It does not open a Deriv WebSocket until this flag is explicitly set to `true` for a parallel smoke test.

## Cutover safety
Do not stop Render's `run_market_stream` command until all of the following pass:
1. Deploy the Django endpoint and this Worker without stopping the existing stream.
2. Confirm active symbol discovery, WebSocket subscriptions, queue throughput, tick freshness, candle creation, snapshot updates, and Channels fan-out.
3. Verify reconnect behaviour and dead-letter handling.
4. Compare ticks received by both streams and confirm duplicate ingestion is harmless.
5. Only then disable the Render stream process.

## Scope
This migrates market-stream connectivity and buffering, while Django remains the authoritative validation/persistence layer. It does not migrate the Celery Python task execution runtime. The separate background scheduler currently dispatches to Celery, so Celery workers cannot be removed until each Python task is ported and tested.
