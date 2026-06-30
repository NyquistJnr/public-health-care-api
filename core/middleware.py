from django.conf import settings
from django.db import connection

from .audit_context import current_request


class TenantHostFallbackMiddleware:
    """
    Re-apply tenant routing from proxy host headers if the request is still on
    public after django-tenants middleware has run.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        public_schema_name = getattr(settings, "PUBLIC_SCHEMA_NAME", "public")
        current_schema = getattr(connection, "schema_name", public_schema_name)

        if current_schema == public_schema_name:
            self.set_tenant_from_known_host(request)

        return self.get_response(request)

    def set_tenant_from_known_host(self, request):
        from tenants.models import Domain

        for hostname in self.get_host_candidates(request):
            domain = Domain.objects.select_related("tenant").filter(domain=hostname).first()
            if domain:
                connection.set_tenant(domain.tenant)
                request.tenant = domain.tenant
                return

    def get_host_candidates(self, request):
        raw_hosts = [
            request.META.get("HTTP_X_FORWARDED_HOST"),
            request.META.get("HTTP_X_ORIGINAL_HOST"),
            request.META.get("HTTP_HOST"),
            request.get_host(),
        ]

        candidates = []
        for raw_host in raw_hosts:
            if not raw_host:
                continue

            for host_part in raw_host.split(","):
                hostname = self.normalize_hostname(host_part)
                if hostname and hostname not in candidates:
                    candidates.append(hostname)

        return candidates

    def normalize_hostname(self, raw_host):
        hostname = raw_host.strip().lower()

        if "://" in hostname:
            hostname = hostname.split("://", 1)[1]

        hostname = hostname.split("/", 1)[0]
        hostname = hostname.rsplit(":", 1)[0]

        return hostname


class AuditContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = current_request.set(request)
        response = self.get_response(request)
        current_request.reset(token)
        return response
