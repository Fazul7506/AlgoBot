# AlgoBot background runtime on Cloudflare Containers

This is the proposed replacement runtime for the three processes removed from the Render web service:

- Celery Worker — Python task execution, with worker concurrency limited to one.
- Celery Beat — the existing Celery schedule, kept as a singleton.
- Deriv Market Stream — the existing Django management command, including its database ingestion and Channels fan-out behavior.

The containers reuse the existing `deploy/external-worker/Dockerfile`; this avoids rewriting Django tasks, AI/model code, database behavior, or the Deriv protocol in JavaScript. Each role has a separate singleton container and an independent resource size. Render remains the web/API service only.

## Deployment gates

**Do not deploy/enable this runtime until all gates below pass.** The existing Cloudflare AI dispatcher is not a substitute for these containers: its webhook enqueues Celery tasks, so a Celery Worker must be running somewhere.

1. Confirm the Cloudflare account has Workers Paid/Containers billing enabled and approve ongoing costs. Containers are not included in the Workers Free plan. This configuration uses a `standard-2` worker container and two `basic` containers; measure usage before increasing sizes.
2. Add the required secrets below to the `algobot-background-runtime` Worker. Never commit values to this repository.
3. Copy the production configuration required by the worker from Render. The allowlist in `src/index.js` must be reviewed against the live Render environment before cutover.
4. Deploy and verify that all three containers start and reconnect after a forced restart.
5. Verify Redis connectivity, database connectivity, task execution, Beat schedules, market tick freshness, and Channels updates.
6. Only after those checks pass, disable any old external worker/Beat/stream processes to prevent duplicate schedules, duplicate broker subscriptions, or duplicate task execution.

## Required Worker secrets

Set these as Worker secrets/environment variables (not in source control):

- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`
- `BREVO_API_KEY`
- `DERIV_OAUTH_CLIENT_ID`
- `DERIV_APP_ID`
- `DERIV_REDIRECT_URI`

Also copy the applicable production settings from Render, including broker/API credentials, notification configuration, R2 model-storage credentials/signing key, encryption keys, and any app-specific values needed by task handlers. The code fails closed if required values are missing.

## Scheduling and recovery

A five-minute Cron Trigger starts or refreshes the stable singleton containers. Container instances can still be stopped by platform events, so each process must tolerate SIGTERM, reconnect to Redis/Deriv, and resume safely. The five-minute trigger is a keepalive/recovery mechanism, not a promise of uninterrupted uptime. Monitor container logs and the application's market-data freshness and queue-depth signals.

The existing Celery Beat schedule remains the source of truth for its current Python tasks. The existing `algobot-ai-training-dispatcher` remains separate; keep its AI Cron Triggers disabled until its webhook and Celery task path are verified.

## Deploy

From this directory:

```sh
npm install
npx wrangler deploy --dry-run
npx wrangler deploy
```

Before deploying, validate the Wrangler configuration and inspect the build output. The Docker build uses the repository root as its context and the existing external-worker Dockerfile. Do not change the Render web start command as part of this container deploy.
