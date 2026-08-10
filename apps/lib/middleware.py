"""Middleware shared by Django HTTP entry points."""

from uuid import uuid4

from apps.lib.log_context import bind_request_id, reset_request_id


class RequestIDMiddleware:
    """Generate and return an opaque request identifier for each HTTP request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = uuid4().hex
        token = bind_request_id(request_id)
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            return response
        finally:
            reset_request_id(token)
