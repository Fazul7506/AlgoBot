# AlgoBot — Tembo Environment

## Project

Django trading platform backed by Deriv APIs. Keep production behavior and existing functionality intact.

## Environment

- Python: 3.12
- Django: use the version resolved by `requirements.txt`
- PostgreSQL and Redis are available in the Tembo VM environment
- Use a project-local virtual environment at `.venv`

## Install

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements.txt
```

Do not use bare `pip`; always use `.venv/bin/python -m pip` so the interpreter and installer are unambiguous.

## Validation

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test --noinput --parallel 1
```

## Django

`manage.py` uses `deriv_platform.settings` as the Django settings module. Do not change that contract unless the task explicitly requires an architecture change.

## Security

- Never hardcode API keys, broker tokens, database passwords, Telegram tokens, OAuth secrets, or other credentials.
- Never print secrets in logs or test output.
- Use environment variables for runtime credentials.
- Do not make production trading/execution depend on Tembo-only services.

## Change discipline

- Diagnose the root cause before changing application code.
- Preserve existing trading, broker, notification, authentication, billing, and API behavior unless the task explicitly targets it.
- Run Django system checks and the relevant tests after changes.
- Prefer small, reviewable changes and keep deployment configuration separate from application logic.
