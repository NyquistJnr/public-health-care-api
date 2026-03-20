# core/audit_context.py
import contextvars

current_request = contextvars.ContextVar('current_request', default=None)

def get_client_ip(request):
    """Accurately extracts IP even if behind Kubernetes/Load Balancers."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'Unknown IP')
