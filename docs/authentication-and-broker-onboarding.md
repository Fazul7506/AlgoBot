# Authentication and broker-onboarding operations

## Mandatory onboarding policy

Password login, API/JWT login, Google login, browser workspace routes, standard JWT API requests, and developer API credentials must not authorize workspace/trading access unless the authenticated AlgoBot user owns a currently eligible, provider-validated Deriv connection. Broker catalog, connect/callback, status, refresh, reconnect, disconnect, authentication recovery, and health paths remain available so a user can complete or repair onboarding. A provider callback alone is not enough: the canonical broker adapter must validate the account connection.

The only production-supported broker adapter currently declared by the project is **Deriv**. Binance, Bybit, OANDA, Interactive Brokers, MT4/MT5 and the other names in `apps/brokers/constants.py` are scaffold entries and must not be presented as production-ready authorization integrations. Disconnect currently disables the local connection and erases AlgoBot-held tokens. This integration does not yet call a documented Deriv token-revocation endpoint; users should revoke provider-side app authorization in their Deriv account settings when required.

## Environment configuration

Set these in the server's secret/configuration manager; never commit populated values:

- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`: existing Google OAuth web-client credentials.
- `GOOGLE_LOGIN_REDIRECT_URI=https://algobot.dpdns.org/auth/google/callback/`: register this exact URI under Authorized redirect URIs for that existing Google OAuth client. Gmail notification OAuth uses the separate `GOOGLE_OAUTH_REDIRECT_URI`.
- `BASE_URL=https://algobot.dpdns.org`: canonical public origin used to build account-verification and password-reset links.
- `DERIV_OAUTH_CLIENT_ID`, `DERIV_APP_ID`, and `DERIV_REDIRECT_URI=https://algobot.dpdns.org/callback/`: Deriv OAuth client, numeric app ID, and exact registered callback. The app ID and OAuth client ID are distinct settings.
- `CREDENTIALS_ENCRYPTION_KEY`: a stable Fernet key stored outside the database and repository. The service can boot without it, but broker credential writes fail closed until it is configured. Back it up securely; losing or rotating it without a planned re-encryption process can make stored credentials unreadable.
- Email delivery: configure the existing Brevo route with `BREVO_API_KEY` and `BREVO_SENDER_EMAIL`, or configure SMTP with `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USER`, and `EMAIL_PASSWORD`. A console email backend is for development only and is not proof of delivery.
- Production infrastructure: configure `SECRET_KEY`, database variables/`DATABASE_URL`, `REDIS_URL`, and the required existing Deriv and payment-provider settings.

Do not paste credential values into PR comments or logs. Google callback URI and provider consent-screen settings must be verified in Google Cloud Console by an authorized operator. Deriv callback registration and a safe provider test account must be verified by an authorized operator. These external checks cannot be inferred from source code or GitHub CI.

## Migration rollback notes

The migrations are additive and reversible, but rollback changes authentication behavior. To reverse only the case-insensitive uniqueness indexes, use `python manage.py migrate core 0006_email_verification_token_expiry`. To also remove the verification-token timestamp field, target `0005_google_identity`. Reversing to `0004_remove_paper_trading` drops the `GoogleIdentity` mapping table and disables persisted Google sign-in mappings; do not do this in production without a database backup and a reviewed identity-migration plan. These commands do not require deleting user accounts.

## Expired-token cleanup

After configuring the key, perform a one-time, non-destructive migration of legacy base64/plaintext token fields (if any exist):

```sh
DJANGO_ENV=production python manage.py reencrypt_broker_credentials
```

This command does not print credential values and validates that the configured key can read already encrypted tokens. Runtime reads of legacy reversible-encoding values fail closed until this migration succeeds. Back up the key securely before running it.

Schedule this non-destructive Django management command using the existing Render Cron/worker process or an equivalent scheduler:

```sh
DJANGO_ENV=production python manage.py cleanup_auth_tokens
```

It deletes expired or already-used password-reset token records and clears expired email-verification token hashes. It does not delete users, broker accounts, trading history, or application tables.

## Existing deployment commands

Keep the established Render/Procfile commands. The Procfile web process runs migrations and static collection before starting Daphne; Render's configured build, pre-deploy, and start commands remain authoritative. Do not run destructive database resets to resolve authentication issues.

## Verification boundary

A green CI run validates only the checks actually executed by that workflow. It does not prove that Google OAuth, Brevo/SMTP delivery, or Deriv authorization works against live providers. Record the exact commit SHA and provider/test environment when completing those checks. Use demo/sandbox broker accounts; never place a live order as part of authentication validation.
