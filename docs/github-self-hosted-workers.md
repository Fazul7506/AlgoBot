# AlgoBot GitHub self-hosted background runtime

This is a **development/learning deployment path** for AlgoBot when Render Background Workers are not available on the Free plan.

It does not replace the canonical Celery architecture in `render.yaml`. It runs the same four existing processes on a GitHub Actions **self-hosted runner**:

- `AlgoBot-Worker`: general Celery queue
- `AlgoBot-Beat`: Celery scheduler
- `AlgoBot-MarketData`: `market_data` queue
- `AlgoBot-LiveMarketStream`: live market stream

GitHub self-hosted runners are free to use, but the machine running the runner is your responsibility. Keep this path for development/learning unless you have a reliable always-on machine and have independently validated its security and availability.

## 1. Add a self-hosted runner

In GitHub:

1. Open `Fazul7506/AlgoBot`.
2. Go to **Settings → Actions → Runners**.
3. Choose **New self-hosted runner**.
4. Select **Linux** and **x64** if the machine is Linux x86_64.
5. Follow GitHub's generated download/configuration commands.
6. Keep the default labels `self-hosted`, `linux`, and `x64`.

GitHub provides the registration token on that page; do not commit it to the repository.

For an always-on Linux machine, GitHub also supports installing the runner application as a service so it starts when the machine boots.

## 2. Add the three required repository secrets

Go to **Settings → Secrets and variables → Actions → New repository secret** and create:

- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`

Use the existing production values only if you understand the security implications of allowing a self-hosted machine to access them.

Do **not** put Deriv account access tokens in this workflow. AlgoBot should continue using its canonical broker-account/token storage and account isolation.

## 3. Start the runtime

Go to:

**Actions → AlgoBot self-hosted background runtime → Run workflow**

The job starts all four processes together and fails if any required process exits.

## Important limitations

This is not a replacement for a managed Render Background Worker:

- the self-hosted machine must remain powered on and connected;
- the GitHub runner must remain online;
- the workflow is intentionally time-bounded;
- the live market stream is unavailable whenever the runner is offline;
- this must not be treated as proof of production uptime.

AlgoBot must continue to expose honest unavailable/stale/disconnected states when these workers are not running. No synthetic market data, signals, balances, orders, positions, or execution results may be introduced to hide worker outages.
