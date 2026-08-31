# AlgoBot Strategy Control Plane

The strategy control plane is now authoritative in `apps.strategies.StrategyConfiguration`.

## State model

- `Strategy` = shared executable strategy catalog entry.
- `StrategyConfiguration` = user-owned execution configuration.
- `criteria` = explicit JSON rule/criteria set.
- `parameters` = engine-specific parameter overrides.
- `broker_account` = account used by the configuration.
- `is_active` = current strategy configuration for the user.

Only one configuration per user is allowed to be active by the control-plane service/command. Account selection remains a separate broker control-plane operation.

## API controls

- `GET /api/strategies/current/` — current strategy and configuration.
- `POST /api/strategies/{id}/switch/` — switch to an enabled configuration.
- `POST /api/strategies/criteria/` — save criteria for a configuration.
- `GET /api/strategies/available/` — catalog plus user configurations.
- `POST /api/strategies/{id}/configure/` — create/update configuration.
- `POST /api/strategies/run/` — execute only the active enabled configuration.

## Terminal controls

```text
python manage.py strategy list --user <USER_ID>
python manage.py strategy current --user <USER_ID>
python manage.py strategy switch --user <USER_ID> --strategy <SLUG>
python manage.py strategy switch --user <USER_ID> --configuration <CONFIG_ID>
python manage.py strategy criteria --user <USER_ID>
python manage.py strategy criteria --user <USER_ID> --configuration <CONFIG_ID> --criteria '{"rsi_min":35,"rsi_max":65}'
```

The command never submits an order. It only changes strategy control-plane state.

## AI failure isolation

AI prediction/recommendation is an enhancement to deterministic strategy execution. If the AI service is unavailable, the deterministic strategy result is preserved and the execution records `ai_error` in its context instead of turning the whole strategy execution into a failure.

Live broker execution remains independently gated by broker connection, account state, and risk controls.
