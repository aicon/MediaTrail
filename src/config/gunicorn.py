bind = "localhost:8001"
preload_app = True
timeout = 200
max_requests = 500
max_requests_jitter = 10

# Nginx already records client access; gunicorn's copy is every request as 127.0.0.1.
accesslog = None
errorlog = "-"
