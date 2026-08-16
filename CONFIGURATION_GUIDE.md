# AlgoBot Enterprise Configuration Guide

This guide documents every owner-managed environment variable discovered in the Django settings, broker, notification, payment, AI, Celery, Redis, and deployment configuration paths. Do not commit real secrets; copy `.env.example` to `.env` and fill values locally or in your production secret manager.

## Manual secrets to generate

- `SECRET_KEY` / `DJANGO_SECRET_KEY`: long random Django signing key.
- `CREDENTIALS_ENCRYPTION_KEY`: long random encryption passphrase/key for stored broker credentials.
- `INTASEND_WEBHOOK_CHALLENGE`: challenge configured for the IntaSend webhook endpoint. `PESAPAL_NOTIFICATION_ID`: IPN ID returned after registering the Pesapal IPN URL.
- `EMAIL_PASSWORD`: SMTP or provider application password when SMTP is enabled.

## API keys to obtain manually

- `DERIV_APP_ID` / `DERIV_OAUTH_CLIENT_ID`: Deriv OAuth application identifier.
- `DERIV_API_TOKEN`: Deriv API token for broker operations that need direct token access.
- `INTASEND_SECRET_KEY`: IntaSend private key for protected status/refund/disbursement APIs. `PESAPAL_CONSUMER_SECRET`: Pesapal merchant secret.
- `BREVO_API_KEY`: Brevo transactional email API key if Brevo notifications are used.
- `TELEGRAM_BOT_TOKEN`: Telegram bot token if Telegram alerts are enabled.
- `OPENAI_API_KEY`: OpenAI API key if AI features require hosted model access.
- `SENTRY_DSN`: Sentry project DSN if error monitoring is enabled.

## External accounts to create before production

- Deriv developer application and production trading account.
- PostgreSQL database service.
- Redis service for cache, Celery, and channel-like realtime workloads.
- SMTP or Brevo email provider account.
- IntaSend merchant account/API keys and webhook challenge.
- Pesapal merchant account/API credentials and registered IPN URL/notification ID.
- Telegram bot and target chat, if Telegram alerts are enabled.
- OpenAI account, if hosted AI inference is enabled.
- Sentry project, if production error telemetry is enabled.

## Production blockers

Production settings now fail fast when these critical values are missing: `SECRET_KEY`, `ALLOWED_HOSTS`, `DATABASE_URL` or complete `POSTGRES_*`, `REDIS_URL`, `BASE_URL`, `DERIV_APP_ID`, and `DERIV_REDIRECT_URI`.

## Variables

| Variable Name | Purpose | Required | Safe Default | Example Format | Where Used | Secret | Development | Testing | Production |
|---|---|---:|---|---|---|---:|---|---|---|
| `SECRET_KEY` | Django and JWT signing key. | Yes | Dev-only insecure fallback | `change-me-long-random` | Django settings, Simple JWT | Yes | Required for realistic local sessions | Can use test value | Required |
| `DJANGO_SECRET_KEY` | Backward-compatible alias for `SECRET_KEY`. | No | Empty | `change-me-long-random` | Django settings fallback | Yes | Optional | Optional | Optional |
| `DEBUG` | Enables Django debug mode. | No | `true` in development | `true` / `false` | Django settings | No | Usually `true` | Usually `false` | Must be `false` |
| `DJANGO_DEBUG` | Backward-compatible alias for `DEBUG`. | No | Empty | `true` / `false` | Django settings fallback | No | Optional | Optional | Optional |
| `ALLOWED_HOSTS` | Comma-separated hosts accepted by Django. | Yes | `127.0.0.1,localhost,testserver` | `app.example.com,www.example.com` | Django host validation | No | Local hosts | `testserver` | Required |
| `BASE_URL` | Public application origin for callbacks and links. | Yes | `http://127.0.0.1:8000` | `https://app.example.com` | OAuth redirects, links | No | Local URL | Test URL | Required |
| `TIME_ZONE` | Django application timezone. | No | `Africa/Nairobi` | `UTC` | Django settings | No | Optional | Optional | Set intentionally |
| `DATABASE_URL` | Full PostgreSQL connection URL. | Production | Empty | `postgres://user:pass@host:5432/db` | Database settings | Yes | Optional | Optional | Recommended/required alternative |
| `USE_POSTGRES` | Enables PostgreSQL settings when no `DATABASE_URL` is supplied. | No | `false` unless URL set | `true` / `false` | Database settings | No | Optional | Optional | Usually `true` |
| `POSTGRES_DB` | PostgreSQL database name. | If using parts | `deriv_platform` | `algobot` | Database settings | No | Optional | Optional | Required if no URL |
| `POSTGRES_USER` | PostgreSQL username. | If using parts | `postgres` | `algobot_user` | Database settings | No | Optional | Optional | Required if no URL |
| `POSTGRES_PASSWORD` | PostgreSQL password. | If using parts | Empty | *(secret)* | Database settings | Yes | Optional | Optional | Required if no URL |
| `POSTGRES_HOST` | PostgreSQL host. | If using parts | `localhost` | `db.example.internal` | Database settings | No | Optional | Optional | Required if no URL |
| `POSTGRES_PORT` | PostgreSQL port. | If using parts | `5432` | `5432` | Database settings | No | Optional | Optional | Required if no URL |
| `REDIS_URL` | Redis URL for cache and Celery defaults. | Production | `redis://localhost:6379/0` | `redis://:pass@host:6379/0` | Cache and Celery settings | Maybe | Local Redis | Optional/eager tasks | Required |
| `USE_REDIS` | Enables Redis cache backend. | No | `false` | `true` / `false` | Cache settings | No | Optional | Optional | Recommended |
| `CELERY_BROKER_URL` | Celery broker URL. | If Celery enabled | `REDIS_URL` | `redis://host:6379/1` | Celery settings | Maybe | Optional | Usually eager | Required if workers run |
| `CELERY_RESULT_BACKEND` | Celery result backend URL. | If Celery enabled | `REDIS_URL` | `redis://host:6379/2` | Celery settings | Maybe | Optional | Usually eager | Required if workers run |
| `USE_CELERY` | Enables Celery-backed task dispatch. | No | `true` | `true` / `false` | Task dispatch | No | Optional | `false`/eager acceptable | Set intentionally |
| `DERIV_APP_ID` | Deriv application ID for OAuth/WebSocket. | Production | Empty | `12345` | Deriv OAuth and WebSocket | No | Required for Deriv testing | Optional | Required |
| `DERIV_OAUTH_CLIENT_ID` | Backward-compatible alias for `DERIV_APP_ID`. | No | Empty | `12345` | Deriv OAuth fallback | No | Optional | Optional | Optional |
| `DERIV_API_TOKEN` | Deriv API authentication token. | If direct broker access enabled | Empty | *(secret)* | Trading and broker services | Yes | Optional | Optional | Required for live direct API use |
| `DERIV_REDIRECT_URI` | Deriv OAuth callback URL. | Production | `${BASE_URL}/callback` | `https://app.example.com/callback` | Deriv OAuth | No | Local callback | Optional | Required |
| `DERIV_API_BASE` | Deriv REST API base URL. | No | `https://api.deriv.com` | `https://api.deriv.com` | Deriv client | No | Default OK | Default OK | Default OK |
| `DEFAULT_FROM_EMAIL` | Default sender address. | If email enabled | `noreply@example.com` | `noreply@example.com` | Email tasks, auth emails | No | Optional | Optional | Required for email |
| `EMAIL_BACKEND` | Django email backend path. | No | Console backend | `django.core.mail.backends.smtp.EmailBackend` | Email settings | No | Console OK | Locmem OK | SMTP/provider backend |
| `EMAIL_HOST` | SMTP host. | If SMTP enabled | Empty | `smtp.example.com` | Email settings | No | Optional | Optional | Required for SMTP |
| `EMAIL_PORT` | SMTP port. | If SMTP enabled | Empty/`587` example | `587` | Email settings | No | Optional | Optional | Required for SMTP |
| `EMAIL_USER` | SMTP username. | If SMTP enabled | Empty | `apikey` or email | Email settings | Maybe | Optional | Optional | Required for SMTP auth |
| `EMAIL_PASSWORD` | SMTP password. | If SMTP enabled | Empty | *(secret)* | Email settings | Yes | Optional | Optional | Required for SMTP auth |
| `BREVO_API_KEY` | Brevo email API key. | If Brevo enabled | Empty | *(secret)* | Notification service | Yes | Optional | Optional | Required for Brevo |
| `BREVO_SENDER_EMAIL` | Brevo sender email. | If Brevo enabled | `DEFAULT_FROM_EMAIL` | `alerts@example.com` | Notification service | No | Optional | Optional | Required for Brevo |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token. | If Telegram enabled | Empty | *(secret)* | Notification service | Yes | Optional | Optional | Required for Telegram |
| `TELEGRAM_CHAT_ID` | Telegram target chat ID. | If Telegram enabled | Empty | `-1001234567890` | Notification service | No | Optional | Optional | Required for Telegram |
| `PAYMENT_PROVIDER` | Default billing provider. | No | `intasend` | `intasend` / `pesapal` | Payment service | No | Optional | Optional | Set intentionally |
| `INTASEND_PUBLIC_KEY` | IntaSend publishable key for checkout creation. | If IntaSend enabled | Empty | *(key)* | Payment service | Yes | Optional | Optional | Obtain from IntaSend dashboard API Keys |
| `INTASEND_SECRET_KEY` | IntaSend private key for protected APIs. | If IntaSend status API used | Empty | *(secret)* | Payment service | Yes | Optional | Optional | Keep server-side only |
| `INTASEND_WEBHOOK_CHALLENGE` | Challenge configured for the IntaSend webhook endpoint. | If IntaSend webhooks enabled | Empty | *(secret)* | Payment webhook | Yes | Optional | Optional | Must match dashboard webhook challenge |
| `PESAPAL_CONSUMER_KEY` | Pesapal API 3.0 merchant consumer key. | If Pesapal enabled | Empty | *(key)* | Payment service | Yes | Optional | Optional | Sent by Pesapal for the merchant account |
| `PESAPAL_CONSUMER_SECRET` | Pesapal API 3.0 merchant consumer secret. | If Pesapal enabled | Empty | *(secret)* | Payment service | Yes | Optional | Optional | Keep server-side only |
| `PESAPAL_NOTIFICATION_ID` | Registered Pesapal IPN identifier. | If Pesapal checkout/webhooks enabled | Empty | *(GUID)* | Payment webhook | Yes | Optional | Optional | Register the public IPN URL first |
| `OPENAI_API_KEY` | OpenAI API key for hosted AI features. | If hosted AI enabled | Empty | *(secret)* | AI settings | Yes | Optional | Optional | Required for hosted AI |
| `SENTRY_DSN` | Sentry telemetry DSN. | No | Empty | `https://key@sentry.io/project` | Logging/monitoring settings | Maybe | Optional | Optional | Recommended |
| `CREDENTIALS_ENCRYPTION_KEY` | Key material for encrypting stored broker credentials. | Production | Empty | *(secret)* | Credential encryption service | Yes | Optional for demo | Optional | Required before storing live credentials |
| `AUDIT_LOG_ENABLED` | Enables audit middleware/service behavior. | No | `true` | `true` / `false` | Security/audit settings | No | Usually `true` | Optional | Required/recommended `true` |
| `TWO_FACTOR_ENABLED` | Enables two-factor authentication features. | No | `true` | `true` / `false` | Security settings | No | Optional | Optional | Recommended `true` |
| `TWO_FACTOR_ISSUER` | Issuer label for two-factor tokens. | No | `DerivBot` | `AlgoBot` | Security settings | No | Optional | Optional | Set to product name |
| `SESSION_COOKIE_SECURE` | Sends session cookies only over HTTPS. | Production | `false` | `true` | Security settings | No | `false` OK | `false` OK | Required `true` |
| `CSRF_COOKIE_SECURE` | Sends CSRF cookies only over HTTPS. | Production | `false` | `true` | Security settings | No | `false` OK | `false` OK | Required `true` |
| `SESSION_COOKIE_SAMESITE` | Session cookie SameSite policy. | No | `Lax` | `Lax` | Security settings | No | Default OK | Default OK | Set intentionally |
| `CSRF_COOKIE_SAMESITE` | CSRF cookie SameSite policy. | No | `Lax` | `Lax` | Security settings | No | Default OK | Default OK | Set intentionally |

## Optional integrations

- **Brevo email:** `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, plus `DEFAULT_FROM_EMAIL`.
- **SMTP email:** `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USER`, `EMAIL_PASSWORD`, `DEFAULT_FROM_EMAIL`.
- **Telegram alerts:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- **IntaSend/Pesapal billing:** `PAYMENT_PROVIDER`, IntaSend API keys/challenge, and Pesapal consumer credentials + notification ID.
- **OpenAI-backed AI features:** `OPENAI_API_KEY`.
- **Sentry monitoring:** `SENTRY_DSN`.
- **Redis cache/Celery:** `REDIS_URL`, `USE_REDIS`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `USE_CELERY`.

---

## Deriv OAuth Configuration

This section provides comprehensive details on Deriv OAuth-specific configuration variables and setup.

### Overview

AlgoBot Enterprise uses OAuth 2.0 with PKCE to securely authenticate users with Deriv. The OAuth implementation includes:

- **PKCE Flow**: Code challenge/verifier pairs for enhanced security
- **State Validation**: CSRF protection through state parameters
- **Token Encryption**: OAuth tokens encrypted at rest in database
- **Automatic Refresh**: Token refresh when approaching expiry
- **Session Management**: Secure session-based OAuth state storage

See [OAUTH_SETUP.md](OAUTH_SETUP.md) for complete OAuth implementation guide.

### OAuth-Specific Variables

#### DERIV_OAUTH_CLIENT_ID (Primary OAuth Variable)

| Attribute | Value |
|-----------|-------|
| **Aliases** | `DERIV_APP_ID` |
| **Purpose** | OAuth application ID from Deriv |
| **Required** | Yes (for OAuth) |
| **Type** | String (numeric) |
| **Secret** | Yes - do not share |
| **Example** | `12345` |
| **Where Used** | OAuth authorization flow, token exchange |
| **Default** | Empty (falls back to `DERIV_APP_ID`) |

**How to Obtain**:
1. Visit [Deriv Developer Dashboard](https://app.deriv.com/account/api-token)
2. Navigate to Settings → OAuth Applications
3. Create new OAuth application
4. Copy the "App ID"

**Configuration**:
```bash
# Environment variable
export DERIV_OAUTH_CLIENT_ID=12345

# Or in settings
DERIV_OAUTH_CLIENT_ID = env("DERIV_OAUTH_CLIENT_ID", env("DERIV_APP_ID", ""))
```

#### DERIV_REDIRECT_URI (OAuth Callback)

| Attribute | Value |
|-----------|-------|
| **Purpose** | OAuth callback endpoint URL |
| **Required** | Yes (for OAuth) |
| **Type** | URL String |
| **Secret** | No - publicly visible |
| **Example Dev** | `http://localhost:8000/callback/` |
| **Example Prod** | `https://algobot.example.com/callback/` |
| **Where Used** | OAuth authorization request, state validation |
| **Default** | `${BASE_URL}/callback` |

**Important Notes**:
- Must exactly match redirect URI registered with Deriv
- Must include trailing slash
- Must be valid HTTP or HTTPS URL
- Cannot use query parameters
- Different per environment (dev, staging, production)

**Configuration**:
```bash
# Environment variable (usually derived from BASE_URL)
export DERIV_REDIRECT_URI=https://algobot.example.com/callback/

# Or in settings
DERIV_REDIRECT_URI = env("DERIV_REDIRECT_URI", f"{BASE_URL}/callback")
```

**Deriv Registration**:
1. Log in to Deriv Developer Dashboard
2. Go to OAuth Applications → Edit your app
3. Add redirect URI under "Authorized URLs"
4. Save changes (may take a few minutes to propagate)

#### CREDENTIALS_ENCRYPTION_KEY (Token Encryption)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Encryption key for storing OAuth tokens |
| **Required** | No (optional but highly recommended) |
| **Type** | Base64-encoded Fernet key |
| **Secret** | Yes - handle securely |
| **Example** | `gAAAAABi3d...` (long base64 string) |
| **Where Used** | `CredentialEncryptionService`, `DerivAccount` model |
| **Default** | Empty (falls back to Base64 encoding) |

**Behavior**:
- If set: Tokens encrypted with Fernet (recommended)
- If not set: Tokens encoded with Base64 (weak, not recommended for production)

**Generate Key**:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Configuration**:
```bash
# Set in environment
export CREDENTIALS_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Or in settings
CREDENTIALS_ENCRYPTION_KEY = env("CREDENTIALS_ENCRYPTION_KEY", "")
```

**Security**:
- Use unique key per environment
- Rotate periodically
- Store in secrets management system (AWS Secrets Manager, Vault, etc.)
- Never commit to version control
- Never share or log the key

#### DERIV_API_TOKEN (Not Used for OAuth)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Direct Deriv API token (NOT for OAuth) |
| **Required** | No (optional, for direct API access) |
| **Type** | String (secret) |
| **Secret** | Yes - do not share |
| **Where Used** | Broker operations, direct API calls |
| **Note** | OAuth does NOT use this; OAuth uses OAuth tokens |

**Important**: Do NOT confuse with OAuth tokens. This is for direct Deriv API access if needed.

### OAuth Configuration by Environment

#### Development

```bash
# .env.local
DEBUG=True
BASE_URL=http://localhost:8000
DERIV_OAUTH_CLIENT_ID=dev-app-id-from-deriv
DERIV_REDIRECT_URI=http://localhost:8000/callback/
CREDENTIALS_ENCRYPTION_KEY=dev-key-optional
```

**Deriv Setup**:
1. Create OAuth app in Deriv (test/sandbox if available)
2. Register redirect URIs:
   - `http://localhost:8000/callback/`
   - `http://127.0.0.1:8000/callback/`

#### Staging

```bash
# .env.staging
DEBUG=False
BASE_URL=https://staging.algobot.example.com
DERIV_OAUTH_CLIENT_ID=staging-app-id
DERIV_REDIRECT_URI=https://staging.algobot.example.com/callback/
CREDENTIALS_ENCRYPTION_KEY=staging-encryption-key
```

**Deriv Setup**:
1. Create separate OAuth app for staging
2. Register redirect URI: `https://staging.algobot.example.com/callback/`

#### Production

```bash
# Production environment variables (never in .env)
DEBUG=False
BASE_URL=https://algobot.example.com
DERIV_OAUTH_CLIENT_ID=production-app-id
DERIV_REDIRECT_URI=https://algobot.example.com/callback/
CREDENTIALS_ENCRYPTION_KEY=production-encryption-key
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_SSL_REDIRECT=True
```

**Deriv Setup**:
1. Create production OAuth app with Deriv
2. Register redirect URI: `https://algobot.example.com/callback/`
3. Use production Deriv servers (not sandbox)

### OAuth Configuration Validation

**Automatic Validation**:
- Runs on application startup in `core/apps.py`
- Checks for required variables: `DERIV_OAUTH_CLIENT_ID`, `DERIV_REDIRECT_URI`, `BASE_URL`
- Logs warning if `CREDENTIALS_ENCRYPTION_KEY` not set
- Fails fast in production if required variables missing

**Manual Validation**:
```bash
python manage.py shell
```

```python
from core.services.oauth_service import DerivOAuthService
is_valid, error = DerivOAuthService.validate_configuration()
print(f"Valid: {is_valid}, Error: {error}")
```

**Production Blockers**:
If running with `DEBUG=False`, these variables are required:
- `DERIV_OAUTH_CLIENT_ID`
- `DERIV_REDIRECT_URI`
- `BASE_URL`

### OAuth API Endpoints

Once configured, these endpoints are available:

| Endpoint | Method | Purpose | Auth Required |
|----------|--------|---------|----------------|
| `/connect-deriv/` | GET | Initiate OAuth login | No |
| `/callback/` | GET | OAuth callback handler | No |
| `/api/deriv/status/` | GET | Get account status | Yes |
| `/api/deriv/disconnect/` | POST | Disconnect account | Yes |
| `/api/deriv/refresh-token/` | POST | Refresh access token | Yes |
| `/api/deriv/reconnect/` | POST | Validate/reconnect account | Yes |

### Common OAuth Configuration Mistakes

1. **Mismatched Redirect URIs**
   - Code: `https://app.com/callback/`
   - Deriv: `https://app.com/callback` (no slash)
   - Solution: Ensure both match exactly (including trailing slash)

2. **Using HTTP in Production**
   - Problem: OAuth over HTTP is insecure
   - Solution: Always use HTTPS in production

3. **Hardcoded Secrets**
   - Problem: Credentials in version control
   - Solution: Use environment variables only

4. **Wrong Encryption Key**
   - Problem: Tokens encrypted with wrong key per server
   - Solution: Use same encryption key for all servers

5. **Missing Deriv Registration**
   - Problem: Redirect URI not registered with Deriv
   - Solution: Register in Deriv Developer Dashboard

### Troubleshooting

**Configuration Errors**:

| Error | Cause | Solution |
|-------|-------|----------|
| "OAuth not configured" | Missing env variables | Set DERIV_OAUTH_CLIENT_ID and DERIV_REDIRECT_URI |
| "State validation failed" | CSRF token mismatch | Check session storage, try incognito mode |
| "Redirect URI mismatch" | Mismatch with Deriv | Register exact URI with Deriv |
| "Token exchange failed" | Network/API issue | Check Deriv API status, retry |
| "Invalid token response" | Deriv returned bad data | Check Deriv API health |

**Debug Mode**:
```bash
# Enable debug logging
LOGGING_LEVEL=DEBUG python manage.py runserver
```

See [OAUTH_SETUP.md](OAUTH_SETUP.md#troubleshooting) for comprehensive troubleshooting guide.

---


## Managed Redis / Redis Cloud

AlgoBot supports managed Redis endpoints through `REDIS_URL`. Use a TLS URL
(`rediss://`) when the provider requires encrypted connections.

Example:

```env
USE_REDIS=true
REDIS_URL=rediss://default:REPLACE_REDIS_PASSWORD@YOUR_REDIS_HOST:YOUR_REDIS_PORT/0
CELERY_BROKER_URL=rediss://default:REPLACE_REDIS_PASSWORD@YOUR_REDIS_HOST:YOUR_REDIS_PORT/0
CELERY_RESULT_BACKEND=rediss://default:REPLACE_REDIS_PASSWORD@YOUR_REDIS_HOST:YOUR_REDIS_PORT/0
```

The market cache uses the complete `REDIS_URL`, including authentication and
TLS settings, instead of assuming `127.0.0.1:6379`.

For a local `.env`, cache/worker variables are read from dotenv without
silently switching the Django database or environment used by management
commands. Verify the connection with:

```bat
python manage.py shell -c "import redis; from django.conf import settings; r=redis.Redis.from_url(settings.REDIS_URL); print(r.ping())"
```

A successful connection prints `True`.
