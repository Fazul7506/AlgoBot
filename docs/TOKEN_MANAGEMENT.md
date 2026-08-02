# Token Management

Broker tokens are stored by `BrokerToken` and encrypted through `CredentialEncryptionService`. Call `set_access_token` and `set_refresh_token`; never assign plaintext tokens directly.
