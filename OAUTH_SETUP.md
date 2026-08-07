# Deriv OAuth Setup Guide

This guide covers the complete setup, configuration, and usage of the Deriv OAuth implementation in AlgoBot Enterprise.

## Table of Contents

1. [Overview](#overview)
2. [Creating a Deriv OAuth Application](#creating-a-deriv-oauth-application)
3. [Environment Configuration](#environment-configuration)
4. [Local Development Setup](#local-development-setup)
5. [Production Setup](#production-setup)
6. [OAuth Flow](#oauth-flow)
7. [API Endpoints](#api-endpoints)
8. [Token Management](#token-management)
9. [Error Handling](#error-handling)
10. [Testing](#testing)
11. [Troubleshooting](#troubleshooting)

## Overview

AlgoBot Enterprise uses OAuth 2.0 with PKCE (Proof Key for Code Exchange) to securely authenticate users with Deriv. This implementation follows OAuth 2.0 and PKCE best practices:

- **PKCE**: Provides additional security by using code challenge/verifier pairs
- **State Parameter**: Prevents CSRF attacks
- **Secure Token Storage**: Tokens are encrypted in the database
- **Token Refresh**: Automatic token refresh when approaching expiry
- **Session Management**: Secure session-based OAuth state storage

## Creating a Deriv OAuth Application

### Step 1: Register with Deriv

1. Visit [Deriv Developer Dashboard](https://app.deriv.com/account/api-token)
2. Sign up or log in to your Deriv account
3. Navigate to Settings → API Tokens

### Step 2: Create OAuth Application

1. In the Deriv Dashboard, go to **Settings** → **OAuth Applications**
2. Click **Create New**
3. Fill in the application details:
   - **App Name**: AlgoBot Enterprise
   - **Description**: Trading bot platform for algorithmic trading
   - **App URL**: Your application's base URL (e.g., `https://algobot.example.com`)
   - **Redirect URLs**: Add your redirect URIs (see [Redirect URI Configuration](#redirect-uri-configuration))

### Step 3: Obtain Credentials

After creating the application, you'll receive:
- **App ID** (OAuth Client ID): Used to identify your application
- **Client Secret**: Keep this secure and never share it

### Step 4: Configure Redirect URIs

Register these redirect URIs with Deriv:

**Development**:
```
http://localhost:8000/callback/
http://127.0.0.1:8000/callback/
```

**Staging**:
```
https://staging.algobot.example.com/callback/
```

**Production**:
```
https://algobot.example.com/callback/
```

## Environment Configuration

### Required Environment Variables

Create a `.env` file in the project root with the following variables:

```bash
# Core Settings
DEBUG=False
SECRET_KEY=your-secret-key-here
BASE_URL=https://algobot.example.com

# Deriv OAuth Configuration
DERIV_OAUTH_CLIENT_ID=your-app-id-from-deriv
DERIV_REDIRECT_URI=https://algobot.example.com/callback/

# Optional: Encryption Key for Token Storage
CREDENTIALS_ENCRYPTION_KEY=your-encryption-key-here
```

### Variable Descriptions

| Variable | Purpose | Required | Example |
|----------|---------|----------|---------|
| `DEBUG` | Django debug mode | Yes | `False` |
| `SECRET_KEY` | Django secret key | Yes | `django-insecure-...` |
| `BASE_URL` | Application base URL | Yes | `https://algobot.example.com` |
| `DERIV_OAUTH_CLIENT_ID` | Deriv App ID | Yes | `12345` |
| `DERIV_REDIRECT_URI` | OAuth callback endpoint | Yes | `https://algobot.example.com/callback/` |
| `CREDENTIALS_ENCRYPTION_KEY` | Encryption key for tokens | No | `base64-encoded-key` |

## Local Development Setup

### Prerequisites

- Python 3.9+
- Django 6.0+
- SQLite (or PostgreSQL)
- `cryptography` package for token encryption

### Step 1: Install Dependencies

```bash
pip install -r requirements/base.txt
pip install cryptography
```

### Step 2: Configure Environment

Create a `.env.local` file:

```bash
DEBUG=True
SECRET_KEY=django-insecure-local-development-only
BASE_URL=http://localhost:8000
DERIV_OAUTH_CLIENT_ID=your-deriv-app-id
DERIV_REDIRECT_URI=http://localhost:8000/callback/
CREDENTIALS_ENCRYPTION_KEY=your-local-encryption-key
```

### Step 3: Generate Encryption Key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy this key to your `.env.local` file as `CREDENTIALS_ENCRYPTION_KEY`.

### Step 4: Run Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### Step 5: Start Development Server

```bash
python manage.py runserver
```

### Step 6: Test OAuth Flow

1. Navigate to `http://localhost:8000/connect-deriv/`
2. You'll be redirected to Deriv's login page
3. Log in with your Deriv account
4. You'll be redirected back to `http://localhost:8000/callback/`
5. On success, you'll be redirected to the dashboard

## Production Setup

### Prerequisites

- Secure HTTPS endpoint
- PostgreSQL database
- Redis cache (for session storage)
- Environment variable management system

### Step 1: Configure Environment

Set these environment variables in your deployment environment:

```bash
DEBUG=False
SECRET_KEY=your-secure-random-secret-key
ALLOWED_HOSTS=algobot.example.com,www.algobot.example.com

# Database
DATABASE_URL=postgresql://user:password@host:5432/algobot

# Cache
REDIS_URL=redis://localhost:6379/0

# Base URL (MUST use HTTPS in production)
BASE_URL=https://algobot.example.com

# Deriv OAuth (register with Deriv using production redirect URI)
DERIV_OAUTH_CLIENT_ID=your-production-app-id
DERIV_REDIRECT_URI=https://algobot.example.com/callback/

# Encryption
CREDENTIALS_ENCRYPTION_KEY=your-production-encryption-key
```

### Step 2: Security Settings

The following security settings are automatically enforced in production:

```python
SESSION_COOKIE_SECURE = True      # Cookies only sent over HTTPS
CSRF_COOKIE_SECURE = True         # CSRF cookies only sent over HTTPS
SECURE_SSL_REDIRECT = True         # Redirect HTTP to HTTPS
SECURE_HSTS_SECONDS = 31536000    # HSTS header
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
```

### Step 3: Run Migrations

```bash
python manage.py migrate
```

### Step 4: Configure Nginx/Apache

Ensure your reverse proxy:
- Passes `X-Forwarded-Proto: https` header
- Passes `X-Forwarded-For` header for client IP
- Sets `Connection: upgrade` for WebSocket support

### Step 5: Monitor OAuth Logs

OAuth events are logged with the `oauth` logger. Configure your logging to capture:

```python
LOGGING = {
    'loggers': {
        'oauth': {
            'level': 'INFO',
            'handlers': ['file'],
        },
    },
}
```

## OAuth Flow

### Complete Authentication Flow

```
┌─────────────┐
│   Browser   │
└────────┬────┘
         │
         │ 1. Click "Connect with Deriv"
         ▼
┌──────────────────────────┐
│  /connect-deriv/         │
│  • Generate PKCE pair    │
│  • Generate state        │
│  • Store in session      │
└────────┬─────────────────┘
         │
         │ 2. Redirect with state & challenge
         ▼
   ┌─────────────────────┐
   │  Deriv OAuth        │
   │  auth.deriv.com     │
   └────────┬────────────┘
         │
         │ 3. User logs in to Deriv
         │
         ▼
   ┌─────────────────────┐
   │  Deriv Login Page   │
   └────────┬────────────┘
         │
         │ 4. Deriv redirects with code
         ▼
┌──────────────────────────┐
│  /callback/              │
│  • Validate state        │
│  • Validate PKCE         │
│  • Exchange code         │
│  • Store tokens          │
│  • Create JWT tokens     │
└────────┬─────────────────┘
         │
         │ 5. Redirect to dashboard
         ▼
┌──────────────────────────┐
│  /dashboard/             │
│  • User authenticated    │
│  • Access JWT tokens     │
└──────────────────────────┘
```

### Key Security Points

1. **State Parameter**: Prevents CSRF by validating state matches between redirect and callback
2. **PKCE**: Prevents authorization code interception attacks
3. **Code Verifier**: Only known to client, used to prove code ownership
4. **Session Storage**: PKCE parameters stored securely in Django session
5. **Token Encryption**: OAuth tokens encrypted at rest in database
6. **HTTPS Only**: OAuth credentials only transmitted over HTTPS in production

## API Endpoints

### 1. Initiate OAuth Login

```http
GET /connect-deriv/
```

Initiates the OAuth flow. User is redirected to Deriv's authorization endpoint.

**Response**: 302 Redirect to Deriv

### 2. OAuth Callback Handler

```http
GET /callback/?code=...&state=...
```

Handles the OAuth callback. Exchanges authorization code for tokens.

**Query Parameters**:
- `code`: Authorization code from Deriv
- `state`: State parameter for CSRF validation
- `error`: (Optional) Error code if authentication failed
- `error_description`: (Optional) Error description

**Response**: 302 Redirect to dashboard on success, or error response on failure

### 3. Disconnect Deriv Account

```http
POST /api/deriv/disconnect/
```

Revokes the current Deriv OAuth connection.

**Authentication**: Required (JWT token)

**Response**:
```json
{
  "status": "success",
  "message": "Deriv account disconnected successfully"
}
```

### 4. Refresh Access Token

```http
POST /api/deriv/refresh-token/
```

Refreshes the access token using the refresh token.

**Authentication**: Required (JWT token)

**Response**:
```json
{
  "status": "success",
  "message": "Token refreshed successfully",
  "expires_at": "2024-08-15T10:30:00Z"
}
```

### 5. Get Account Status

```http
GET /api/deriv/status/
```

Returns the current Deriv OAuth account status.

**Authentication**: Required (JWT token)

**Response**:
```json
{
  "status": "success",
  "account": {
    "account_id": "1234567",
    "account_type": "demo",
    "currency": "USD",
    "token_status": "active",
    "is_token_expired": false,
    "needs_refresh": false,
    "expires_at": "2024-08-15T10:30:00Z",
    "last_refresh": "2024-08-01T10:30:00Z",
    "connected_at": "2024-07-15T08:00:00Z"
  }
}
```

### 6. Reconnect Deriv Account

```http
POST /api/deriv/reconnect/
```

Validates current connection or initiates reconnection.

**Authentication**: Required (JWT token)

**Response**:
```json
{
  "status": "success",
  "message": "Reconnected successfully",
  "requires_oauth": false
}
```

Or if re-authentication is required:
```json
{
  "status": "success",
  "message": "Full re-authentication required",
  "requires_oauth": true,
  "oauth_url": "/connect-deriv/"
}
```

## Token Management

### Token Storage

Tokens are encrypted in the database using the `CredentialEncryptionService`:

- **Algorithm**: Fernet (symmetric encryption)
- **Key Source**: `CREDENTIALS_ENCRYPTION_KEY` environment variable
- **Fallback**: Base64 encoding if encryption key not available

### Token Encryption

The `DerivAccount` model provides encryption methods:

```python
from trading.models import DerivAccount

# Store encrypted token
deriv_account = DerivAccount.objects.get(user=user)
deriv_account.set_access_token(access_token)
deriv_account.set_refresh_token(refresh_token)
deriv_account.save()

# Retrieve decrypted token
access_token = deriv_account.get_access_token()
refresh_token = deriv_account.get_refresh_token()
```

### Token Expiry and Refresh

Tokens are automatically tracked for expiry:

```python
deriv_account = DerivAccount.objects.get(user=user)

# Check if expired
if deriv_account.is_token_expired:
    # Token has expired
    pass

# Check if needs refresh (within 5 minutes of expiry)
if deriv_account.needs_refresh:
    # Refresh token before it expires
    pass
```

## Error Handling

### OAuth Errors from Deriv

When Deriv returns an error, the callback endpoint will display the error:

| Error Code | Meaning | Solution |
|----------|---------|----------|
| `invalid_request` | Invalid request | Check redirect URI and parameters |
| `unauthorized_client` | Client not authorized | Verify App ID with Deriv |
| `access_denied` | User denied permission | User chose not to authorize |
| `unsupported_response_type` | Response type not supported | Verify OAuth implementation |
| `invalid_scope` | Invalid scope requested | Ensure scope is 'trade' |
| `server_error` | Deriv server error | Retry after waiting |

### Common Application Errors

| Error | Cause | Solution |
|-------|-------|----------|
| "OAuth is not configured" | Missing environment variables | Set DERIV_OAUTH_CLIENT_ID and DERIV_REDIRECT_URI |
| "OAuth state validation failed" | CSRF token mismatch | Ensure no proxy/middleware modifying cookies |
| "PKCE validation failed" | Session lost | Check session storage configuration |
| "Token exchange timed out" | Deriv API slow/offline | Retry connection |
| "Invalid token response" | Deriv returned unexpected data | Check Deriv API status |

### Error Response Format

All errors return appropriate HTTP status codes and JSON responses:

```json
{
  "status": "error",
  "message": "Descriptive error message"
}
```

Common status codes:
- `400`: Bad Request (missing/invalid parameters)
- `404`: Not Found (account not connected)
- `502`: Bad Gateway (Deriv API error)
- `503`: Service Unavailable (OAuth not configured)
- `504`: Gateway Timeout (Deriv API timeout)

## Testing

### Manual Testing Checklist

- [ ] OAuth login initiates correctly
- [ ] Redirects to Deriv login page
- [ ] Can log in with test Deriv account
- [ ] Callback processes authorization code
- [ ] Tokens stored encrypted in database
- [ ] JWT tokens generated for frontend
- [ ] Redirect to dashboard works
- [ ] Account status endpoint returns correct data
- [ ] Token refresh endpoint works
- [ ] Disconnect endpoint revokes account
- [ ] Reconnect endpoint validates connection
- [ ] State validation catches CSRF attempts
- [ ] PKCE validation catches tampering

### Unit Test Example

```python
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest.mock import patch, Mock

@override_settings(
    DERIV_OAUTH_CLIENT_ID="test-app-id",
    DERIV_REDIRECT_URI="http://testserver/callback/"
)
class DerivOAuthTests(TestCase):
    
    def test_login_generates_state_and_pkce(self):
        response = self.client.get(reverse('connect_deriv'))
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('oauth_state', self.client.session)
        self.assertIn('pkce_verifier', self.client.session)
    
    @patch('core.services.oauth_service.requests.post')
    def test_callback_exchanges_code(self, mock_post):
        # Setup session
        session = self.client.session
        session['oauth_state'] = 'test-state'
        session['pkce_verifier'] = 'test-verifier'
        session['oauth_redirect_uri'] = 'http://testserver/callback/'
        session.save()
        
        # Mock Deriv response
        mock_response = Mock()
        mock_response.json.return_value = {
            'access_token': 'test-token',
            'refresh_token': 'test-refresh',
            'account_id': '123456',
            'expires_in': 3600
        }
        mock_post.return_value = mock_response
        
        # Call callback
        response = self.client.get(
            reverse('callback'),
            {'state': 'test-state', 'code': 'test-code'}
        )
        
        # Verify token exchange
        mock_post.assert_called_once()
        self.assertEqual(response.status_code, 302)
```

### Integration Test

```python
def test_complete_oauth_flow():
    # 1. Initiate login
    response = client.get('/connect-deriv/')
    assert response.status_code == 302
    
    # 2. Simulate Deriv callback
    response = client.get(
        '/callback/',
        {
            'code': 'auth-code-123',
            'state': 'state-from-login'
        }
    )
    assert response.status_code == 302
    
    # 3. Check user authenticated
    user = User.objects.get(username='deriv_123456')
    assert user is not None
    
    # 4. Check tokens stored
    deriv_account = DerivAccount.objects.get(user=user)
    assert deriv_account.access_token is not None
    assert deriv_account.expires_at > timezone.now()
```

## Troubleshooting

### Problem: "OAuth is not configured"

**Cause**: Missing environment variables

**Solution**:
```bash
# Check environment variables
echo $DERIV_OAUTH_CLIENT_ID
echo $DERIV_REDIRECT_URI

# Set them if missing
export DERIV_OAUTH_CLIENT_ID=your-app-id
export DERIV_REDIRECT_URI=http://localhost:8000/callback/
```

### Problem: Redirect to Deriv fails silently

**Cause**: Invalid OAuth configuration with Deriv

**Solution**:
1. Verify App ID is correct
2. Verify redirect URI is registered with Deriv
3. Check Deriv Developer Dashboard for OAuth app status

### Problem: "OAuth state validation failed"

**Cause**: Session lost between requests

**Solution**:
1. Check session middleware is configured correctly
2. Verify cookies are being transmitted (check browser dev tools)
3. Check for proxy/load balancer modifying cookies
4. Try in incognito/private window

### Problem: Tokens not persisting

**Cause**: Database migration not run

**Solution**:
```bash
python manage.py migrate
```

### Problem: "Deriv API timeout"

**Cause**: Network connectivity or Deriv service slow

**Solution**:
1. Check internet connection
2. Check Deriv API status page
3. Increase timeout in `DerivOAuthService.OAUTH_TIMEOUT`
4. Retry authentication

### Problem: Encryption key issues

**Cause**: Invalid or missing encryption key

**Solution**:
```bash
# Generate new key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Set in environment
export CREDENTIALS_ENCRYPTION_KEY=your-key
```

### Debugging Tips

Enable debug logging:

```python
# settings.py
LOGGING = {
    'loggers': {
        'oauth': {
            'level': 'DEBUG',
            'handlers': ['console'],
        },
    },
}
```

Check session data in Django shell:

```bash
python manage.py shell

from django.contrib.sessions.models import Session
from django.contrib.auth.models import User

# Get most recent session
session = Session.objects.latest('expire_date')
data = session.get_decoded()
print(data)
```

Monitor database tokens:

```bash
python manage.py shell

from trading.models import DerivAccount
from django.contrib.auth.models import User

user = User.objects.get(username='deriv_123456')
account = DerivAccount.objects.get(user=user)
print(f"Status: {account.token_status}")
print(f"Expired: {account.is_token_expired}")
print(f"Needs Refresh: {account.needs_refresh}")
```

## Support

For issues with:

- **Deriv OAuth**: Contact [Deriv Support](https://deriv.com/contact-us)
- **AlgoBot OAuth Implementation**: Check this documentation
- **Database/Encryption**: Check Django logs
- **Network/Proxy**: Check reverse proxy configuration

---

**Last Updated**: 2024-08-07
**Version**: 1.0
