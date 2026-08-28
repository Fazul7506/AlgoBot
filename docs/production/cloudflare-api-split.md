# AlgoBot public UI / dedicated API split

## Goal

Keep `algobot.dpdns.org` behind the normal Cloudflare browser protection while moving browser API calls to `api.algobot.dpdns.org`, which must be **DNS-only** at the DNS provider. This prevents Cloudflare browser challenges from sitting in front of AI, broker, backtesting, and billing API requests.

## Render

The Blueprint now registers both custom domains on the AlgoBot web service:

- `algobot.dpdns.org`
- `api.algobot.dpdns.org`

Render automatically provisions TLS for configured custom domains. Add/verify both domains in the Render service Custom Domains section if they are not already present.

## Cloudflare DNS

Keep Cloudflare nameservers. Add/verify the API hostname as a CNAME to the **same Render `onrender.com` hostname used by AlgoBot**, but set the API record to **DNS only (grey cloud)**.

Keep the public UI record (`algobot.dpdns.org`) proxied (orange cloud) if you want Cloudflare protection for the website.

Do not create an AAAA record for the Render service.

## Render environment variables

Set these on the production AlgoBot web service:

```text
ALGO_API_BASE_URL=https://api.algobot.dpdns.org
CORS_ALLOWED_ORIGINS=https://algobot.dpdns.org
CSRF_TRUSTED_ORIGINS=https://algobot.dpdns.org
SESSION_COOKIE_DOMAIN=.algobot.dpdns.org
CSRF_COOKIE_DOMAIN=.algobot.dpdns.org
SESSION_COOKIE_SECURE=true
CSRF_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=Lax
CSRF_COOKIE_SAMESITE=Lax
```

Keep the existing production `ALLOWED_HOSTS` value and ensure it includes both `algobot.dpdns.org` and `api.algobot.dpdns.org`.

## Browser behavior

The shared frontend runtime automatically uses `https://api.algobot.dpdns.org` when the public site is `algobot.dpdns.org`. Local/development deployments remain same-origin and retain the `/data/` fallback.

## Verification order

1. Add/verify both custom domains in Render.
2. Create the API CNAME in Cloudflare and set it DNS-only.
3. Set the production environment variables above.
4. Wait for DNS/TLS verification.
5. Open `https://api.algobot.dpdns.org/health/` and confirm the API responds without a Cloudflare browser challenge.
6. Open the AlgoBot terminal and confirm market data, AI analysis, order preview, and order submission use the API hostname.
7. Only after all automated CI checks and the live smoke tests pass should live trading be re-enabled.
