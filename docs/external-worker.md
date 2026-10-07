# AlgoBot external worker runtime

The external Linux host runs the existing general Celery worker, market-data Celery worker, Celery Beat, and live market stream. Render remains the Django web/API service. Both use the same production Redis broker and PostgreSQL database. No duplicate trading or market-data architecture is introduced.

Recommended no-cost host: Oracle Cloud Infrastructure Always Free Linux VM. Oracle currently documents 2 OCPUs and 12 GB memory total for Always Free Ampere A1 compute, subject to capacity and eligibility.

Configure /etc/algobot/worker.env with DJANGO_ENV=production, USE_REDIS=true, USE_CELERY=true, DATABASE_URL, REDIS_URL, CELERY_BROKER_URL, CELERY_RESULT_BACKEND, and SECRET_KEY. The two Celery URLs must equal REDIS_URL.

Do not run migrations from the worker host. Render remains the migration owner. Never commit worker.env or broker credentials. Production validation must confirm Redis connectivity, task consumption, market-stream activity, database writes, and Signals/Analysis API state.
