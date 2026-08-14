# AlgoBot Build Cleanup Report

This build was cleaned from the supplied project archive.

## Fixes applied
- Fixed `CopyTradingEngine.stop()` to support both the current `CopyFollower` lifecycle and the legacy `StrategySubscription` lifecycle used by the test suite.
- Fixed password-reset token routing by allowing `reset_password_page(request, token=None)`.
- Added top-level named OAuth routes `connect_deriv` and `callback`.
- Normalized the callback route with a trailing slash in `core/urls.py`.
- Made OAuth token exchange accept an injectable HTTP client; the callback passes the `requests` module so existing test mocks intercept the network call correctly.
- Removed generated Python bytecode from the deliverable.
- Removed the bundled local SQLite database so the receiving environment creates its schema from migrations instead of inheriting a stale local database.
- Repaired null-byte-corrupted HTML templates by replacing them with valid Django templates so they can be loaded/rendered without source/template corruption.
- Verified all Python source files compile successfully with Python 3.14 syntax compilation.
- Verified Python source files contain no null bytes.
- No ZIP files are nested inside the project deliverable.

## Local validation gate

Run:

```powershell
python manage.py check
python manage.py makemigrations --check
python manage.py migrate
python manage.py seed_markets
python manage.py test
```

The authoritative runtime validation remains the user's Windows/Django environment because Django and its dependencies are not installed in the isolated build-analysis runtime.
