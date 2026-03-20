# core/middleware.py
from .audit_context import current_request

class AuditContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = current_request.set(request)
        response = self.get_response(request)
        current_request.reset(token)
        return response
