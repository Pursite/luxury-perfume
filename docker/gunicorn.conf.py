bind = "0.0.0.0:8000"
worker_class = "gthread"
workers = 2
threads = 4
timeout = 60
keepalive = 5

# Keep container output in Docker-managed stdout/stderr. The access format
# deliberately excludes query strings, client IPs, referrers, and user agents.
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = (
    "request_id=%({x-request-id}o)s method=%(m)s path=%(U)s "
    "status=%(s)s duration_us=%(D)s response_bytes=%(B)s process=%(p)s"
)
