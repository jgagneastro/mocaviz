"""Linux production profile; no credentials or request/response files.

Set MOCAVIZ_GNIRS_CACHE_FILE to the one existing private SQLite file before
starting. Keep this backend on loopback, behind HTTPS with the Nginx snippet.
"""
bind = '127.0.0.1:8796'
workers = 2
worker_class = 'gthread'
threads = 4
timeout = 180
graceful_timeout = 30
# A rebuild runs in its accepting worker. Do not recycle workers mid-refresh.
max_requests = 0
preload_app = False
# Gunicorn heartbeat files stay in Linux shared memory, created at startup.
worker_tmp_dir = '/dev/shm'
accesslog = None
errorlog = '/dev/null'
capture_output = False
disable_redirect_access_to_syslog = True
