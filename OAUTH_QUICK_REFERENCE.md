# Quick Reference: Deriv OAuth Implementation

**Last Updated**: 2024-08-07

---

## 🚀 Quick Start

### Development

```bash
# 1. Set environment variables
export DERIV_OAUTH_CLIENT_ID=your-app-id
export DERIV_REDIRECT_URI=http://localhost:8000/callback/
export CREDENTIALS_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# 2. Run migrations
python manage.py migrate

# 3. Start server
python manage.py runserver

# 4. Test OAuth flow
# Navigate to: http://localhost:8000/connect-deriv/
```

### Production

```bash
# 1. Set environment variables (use your secrets manager)
export DERIV_OAUTH_CLIENT_ID=prod-app-id
export DERIV_REDIRECT_URI=https://algobot.example.com/callback/
export CREDENTIALS_ENCRYPTION_KEY=production-encryption-key

# 2. Run migrations
python manage.py migrate

# 3. Collect static files
python manage.py collectstatic

# 4. Start gunicorn/uwsgi
gunicorn deriv_platform.wsgi
```

---

## 📋 Configuration Variables

| Variable | Required | Example | Purpose |
|----------|----------|---------|---------|
| DERIV_OAUTH_CLIENT_ID | Yes | `12345` | OAuth app ID from Deriv |
| DERIV_REDIRECT_URI | Yes | `https://example.com/callback/` | OAuth callback URL |
| BASE_URL | Yes | `https://example.com` | Application base URL |
| CREDENTIALS_ENCRYPTION_KEY | No | (base64 key) | Token encryption key |

**Get from**:
- DERIV_OAUTH_CLIENT_ID: [Deriv Developer Dashboard](https://app.deriv.com/account/api-token)
- DERIV_REDIRECT_URI: Your application callback URL
- BASE_URL: Your application URL
- CREDENTIALS_ENCRYPTION_KEY: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

---

## 🔗 Key Files

| File | Purpose | Key Changes |
|------|---------|-------------|
| `core/services/oauth_service.py` | OAuth service | NEW - 15+ methods |
| `core/views_oauth.py` | OAuth API | NEW - 4 endpoints |
| `core/views.py` | OAuth views | Updated - uses service |
| `trading/models/core.py` | DerivAccount | Updated - encryption |
| `OAUTH_SETUP.md` | Setup guide | NEW - 600+ lines |
| `CONFIGURATION_GUIDE.md` | Config ref | Updated - OAuth section |

---

## 🌐 API Endpoints

### OAuth Flow

```
GET /connect-deriv/
  → Redirects to Deriv login

GET /callback/?code=...&state=...
  → Handles OAuth callback
  → Creates/updates user
  → Redirects to dashboard
```

### API (Authenticated)

```
GET /api/deriv/status/
  → Returns account status

POST /api/deriv/refresh-token/
  → Refreshes access token

POST /api/deriv/disconnect/
  → Revokes OAuth

POST /api/deriv/reconnect/
  → Validates connection
```

---

## 🔐 Security

### Encryption

```python
from trading.models import DerivAccount

account = DerivAccount.objects.get(user=user)

# Store encrypted
account.set_access_token(access_token)
account.save()

# Retrieve decrypted
token = account.get_access_token()
```

### Token Status

```python
account.token_status  # active/expired/revoked/refreshing
account.is_token_expired  # Check expiry
account.needs_refresh  # Check if needs refresh (5-min buffer)
```

---

## 📝 Common Tasks

### Check Configuration

```bash
python manage.py shell
```

```python
from core.services.oauth_service import DerivOAuthService
is_valid, error = DerivOAuthService.validate_configuration()
print(f"Valid: {is_valid}, Error: {error}")
```

### Generate Encryption Key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### View Stored Tokens

```bash
python manage.py shell
```

```python
from trading.models import DerivAccount
from django.contrib.auth.models import User

user = User.objects.get(username='deriv_123456')
account = DerivAccount.objects.get(user=user)
print(f"Account: {account.account_id}")
print(f"Status: {account.token_status}")
print(f"Expired: {account.is_token_expired}")
print(f"Needs Refresh: {account.needs_refresh}")
```

### Manually Refresh Token

```bash
python manage.py shell
```

```python
from trading.models import DerivAccount
from core.services.oauth_service import DerivOAuthService
from django.contrib.auth.models import User

user = User.objects.get(username='deriv_123456')
account = DerivAccount.objects.get(user=user)
refresh_token = account.get_refresh_token()

success, token_data, error = DerivOAuthService.refresh_access_token(refresh_token)
if success:
    account.set_access_token(token_data['access_token'])
    account.expires_at = DerivOAuthService.parse_token_expiry(
        int(token_data.get('expires_in', 3600))
    )
    account.save()
    print("Token refreshed successfully")
else:
    print(f"Refresh failed: {error}")
```

### Disconnect Account

```bash
curl -X POST http://localhost:8000/api/deriv/disconnect/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json"
```

### Get Account Status

```bash
curl -X GET http://localhost:8000/api/deriv/status/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## 🐛 Debugging

### Enable Debug Logging

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

### Check Session Data

```bash
python manage.py shell
```

```python
from django.contrib.sessions.models import Session

session = Session.objects.latest('expire_date')
data = session.get_decoded()
print(f"oauth_state: {data.get('oauth_state')}")
print(f"pkce_verifier: {data.get('pkce_verifier')}")
print(f"oauth_redirect_uri: {data.get('oauth_redirect_uri')}")
```

### Monitor OAuth Logs

```bash
tail -f logs/oauth.log | grep deriv_oauth
```

---

## ⚠️ Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| "OAuth not configured" | Missing env vars | Set DERIV_OAUTH_CLIENT_ID, DERIV_REDIRECT_URI |
| "State validation failed" | CSRF token mismatch | Try incognito mode, check cookies |
| "Redirect URI mismatch" | URL mismatch | Ensure exact match with Deriv registration |
| "Token exchange timed out" | Network/Deriv slow | Retry, check Deriv status |
| "No refresh token available" | Account never refreshed | Set up token refresh |
| "No Deriv account connected" | Account not linked | Run OAuth flow first |

---

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| [OAUTH_SETUP.md](OAUTH_SETUP.md) | Complete setup guide (600+ lines) |
| [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) | Configuration reference |
| [OAUTH_AUDIT_REPORT.md](OAUTH_AUDIT_REPORT.md) | Audit and architecture |
| [OAUTH_IMPLEMENTATION_SUMMARY.md](OAUTH_IMPLEMENTATION_SUMMARY.md) | Implementation details |

---

## 🔄 OAuth Flow Diagram

```
┌─────────────────┐
│ User Browser    │
└────────┬────────┘
         │ Click "Connect with Deriv"
         ▼
    /connect-deriv/
         │ Generate state & PKCE
         ▼
   Redirect to Deriv OAuth
         │ User logs in
         ▼
    /callback/?code=XXX&state=YYY
         │ Validate & exchange
         ▼
  /dashboard/?access=JWT
         │ User authenticated
         ▼
    ✅ Ready to Trade
```

---

## 📊 Database Schema

### DerivAccount Model

```python
class DerivAccount(models.Model):
    user = OneToOneField(User)
    account_id = CharField(max_length=50)
    access_token = TextField()  # Encrypted
    refresh_token = TextField()  # Encrypted
    token_status = CharField()  # active/expired/revoked/refreshing
    expires_at = DateTimeField()
    last_refresh = DateTimeField()
    account_type = CharField()  # demo/real
    currency = CharField()
    created_at = DateTimeField()
    updated_at = DateTimeField()
```

---

## 🎯 Service Methods

### DerivOAuthService

**Configuration**:
- `validate_configuration()` - Validate settings

**PKCE**:
- `generate_pkce_pair()` - Create verifier/challenge
- `generate_state()` - Create state parameter

**URLs**:
- `create_authorization_url()` - Build OAuth URL

**Validation**:
- `validate_state()` - Validate CSRF token
- `validate_pkce()` - Validate code verifier
- `validate_token_response()` - Validate token data

**Token Exchange**:
- `exchange_code_for_token()` - Exchange code for tokens
- `refresh_access_token()` - Refresh expired token
- `parse_token_expiry()` - Calculate expiry time
- `is_token_expired()` - Check if expired

**Session**:
- `store_oauth_state_in_session()` - Store state
- `clear_oauth_session()` - Clear state

---

## 🚨 Health Check

```bash
# 1. Verify configuration
python manage.py shell
from core.services.oauth_service import DerivOAuthService
is_valid, error = DerivOAuthService.validate_configuration()
assert is_valid, error

# 2. Verify database migration
python manage.py showmigrations trading | grep DerivAccount

# 3. Check encryption key
python -c "from django.conf import settings; print('Encryption key set' if settings.CREDENTIALS_ENCRYPTION_KEY else 'WARNING: No encryption key')"

# 4. Test OAuth endpoints
curl http://localhost:8000/connect-deriv/  # Should redirect
curl http://localhost:8000/api/deriv/status/ -H "Authorization: Bearer TOKEN"  # Should work if authenticated
```

---

## 📞 Support

| Topic | Resource |
|-------|----------|
| Setup help | [OAUTH_SETUP.md](OAUTH_SETUP.md#troubleshooting) |
| Configuration issues | [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) |
| Architecture questions | [OAUTH_AUDIT_REPORT.md](OAUTH_AUDIT_REPORT.md) |
| Implementation details | [OAUTH_IMPLEMENTATION_SUMMARY.md](OAUTH_IMPLEMENTATION_SUMMARY.md) |
| Code documentation | Read docstrings in `core/services/oauth_service.py` |

---

**Status**: ✅ Production Ready  
**Last Verified**: 2024-08-07  
**Next Review**: 2024-12-07
