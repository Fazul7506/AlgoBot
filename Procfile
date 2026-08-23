web: gunicorn deriv_platform.wsgi:application --bind 0.0.0.0:$PORT --workers ${WEB_CONCURRENCY:-2} --threads 2 --timeout 60 --graceful-timeout 30 --keep-alive 5 --access-logfile - --error-logfile -
