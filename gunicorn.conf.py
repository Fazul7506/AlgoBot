import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
workers = int(os.getenv('WEB_CONCURRENCY', '2'))
threads = 2
timeout = 60
graceful_timeout = 30
keepalive = 5
accesslog = '-'
errorlog = '-'
worker_tmp_dir = '/dev/shm' if os.path.isdir('/dev/shm') else None
