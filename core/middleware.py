from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.utils import timezone

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
        request.tenant_host_fallback = {
            "attempted": current_schema == public_schema_name,
            "candidates": [],
            "matched_host": None,
            "matched_schema": None,
        }

        if current_schema == public_schema_name:
            self.set_tenant_from_known_host(request)

        return self.get_response(request)

    def set_tenant_from_known_host(self, request):
        from tenants.models import Domain, State

        for hostname in self.get_host_candidates(request):
            request.tenant_host_fallback["candidates"].append(hostname)
            domain = Domain.objects.select_related("tenant").filter(domain=hostname).first()
            if domain:
                connection.set_tenant(domain.tenant)
                request.tenant = domain.tenant
                request.tenant_host_fallback["matched_host"] = hostname
                request.tenant_host_fallback["matched_schema"] = domain.tenant.schema_name
                return

        default_schema = getattr(settings, "DEFAULT_TENANT_SCHEMA", None)
        if default_schema:
            tenant = State.objects.filter(schema_name=default_schema).first()
            if tenant:
                connection.set_tenant(tenant)
                request.tenant = tenant
                request.tenant_host_fallback["matched_host"] = "__default__"
                request.tenant_host_fallback["matched_schema"] = tenant.schema_name

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


class ActivityTrackingMiddleware:
    """
    Stamps User.last_active, maintains idle-timeout UserSession rows, and logs
    ModuleUsageLog entries for requests under a tracked module path. Runs after
    the view so DRF has resolved request.user (DRF's Request.user setter syncs
    the authenticated user back onto the underlying Django request).
    """

    IDLE_TIMEOUT = timedelta(minutes=30)
    WRITE_THROTTLE = timedelta(seconds=60)

    MODULE_PATH_MAP = [
        ('/api/v1/patients/', 'PATIENT_REGISTRY'),
        ('/api/v1/appointments/', 'PATIENT_RECORDS'),
        ('/api/v1/consultations/', 'PATIENT_RECORDS'),
        ('/api/v1/immunization/', 'PATIENT_RECORDS'),
        ('/api/v1/maternal-care/', 'PATIENT_RECORDS'),
        ('/api/v1/referrals/', 'PATIENT_RECORDS'),
        ('/api/v1/adverse-events/', 'PATIENT_RECORDS'),
        ('/api/v1/doctor/', 'PATIENT_RECORDS'),
        ('/api/v1/nurse/', 'PATIENT_RECORDS'),
        ('/api/v1/prescriptions/', 'PHARMACY'),
        ('/api/v1/laboratory/', 'LAB'),
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            self._track(request, user)

        return response

    def _track(self, request, user):
        from .models import ModuleUsageLog, UserSession
        from django.db.utils import ProgrammingError, OperationalError

        now = timezone.now()
        
        try:
            facility = getattr(user, 'facility', None)
        except (ProgrammingError, OperationalError):
            facility = None

        try:
            if not user.last_active or now - user.last_active >= self.WRITE_THROTTLE:
                type(user).objects.filter(pk=user.pk).update(last_active=now)

            session = UserSession.objects.filter(user=user, ended_at__isnull=True).order_by('-last_active_at').first()
            if session and now - session.last_active_at <= self.IDLE_TIMEOUT:
                if now - session.last_active_at >= self.WRITE_THROTTLE:
                    session.last_active_at = now
                    session.save(update_fields=['last_active_at'])
            else:
                if session:
                    session.ended_at = session.last_active_at
                    session.save(update_fields=['ended_at'])
                UserSession.objects.create(user=user, facility=facility, started_at=now, last_active_at=now)

            module = self._resolve_module(request.path)
            if module:
                ModuleUsageLog.objects.create(user=user, facility=facility, module=module)
        except (ProgrammingError, OperationalError):
            pass

    def _resolve_module(self, path):
        for prefix, module in self.MODULE_PATH_MAP:
            if path.startswith(prefix):
                return module
        return None
