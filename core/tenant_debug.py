from django.conf import settings
from django.http import Http404, JsonResponse
from django.utils.crypto import constant_time_compare
from django.db import connection


CRITICAL_TABLES = (
    "core_user",
    "core_patientprofile",
    "facilities_facility",
    "appointments_appointment",
    "appointments_vitals",
    "referrals_referral",
)


def tenant_debug_view(request):
    token = getattr(settings, "TENANT_DEBUG_TOKEN", "")
    supplied_token = request.headers.get("X-Tenant-Debug-Token") or request.GET.get("token", "")

    if not token or not constant_time_compare(str(token), str(supplied_token)):
        raise Http404()

    schema_name = getattr(connection, "schema_name", "public")

    return JsonResponse(
        {
            "schema_name": schema_name,
            "tenant": getattr(getattr(request, "tenant", None), "schema_name", None),
            "host": request.get_host(),
            "headers": {
                "host": request.META.get("HTTP_HOST"),
                "x_forwarded_host": request.META.get("HTTP_X_FORWARDED_HOST"),
                "x_original_host": request.META.get("HTTP_X_ORIGINAL_HOST"),
            },
            "fallback": getattr(request, "tenant_host_fallback", None),
            "database": get_database_context(),
            "domain_routes": get_domain_routes(),
            "tables": get_table_status(schema_name),
        }
    )


def get_database_context():
    with connection.cursor() as cursor:
        cursor.execute("select current_database(), current_schema(), current_setting('search_path')")
        database_name, current_schema, search_path = cursor.fetchone()

    return {
        "name": database_name,
        "current_schema": current_schema,
        "search_path": search_path,
    }


def get_domain_routes():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select d.domain, s.schema_name, d.is_primary
            from public.tenants_domain d
            join public.tenants_state s on s.id = d.tenant_id
            where d.domain in (
                'primary-health-care-api.vercel.app',
                'public-health-care-api.vercel.app'
            )
            order by d.domain
            """
        )
        rows = cursor.fetchall()

    return [
        {
            "domain": domain,
            "schema_name": schema_name,
            "is_primary": is_primary,
        }
        for domain, schema_name, is_primary in rows
    ]


def get_table_status(schema_name):
    statuses = {}
    schemas = ("public", schema_name)

    with connection.cursor() as cursor:
        for table in CRITICAL_TABLES:
            statuses[table] = {}
            for current_schema in schemas:
                qualified_table = f"{current_schema}.{table}"
                cursor.execute("select to_regclass(%s)", [qualified_table])
                statuses[table][current_schema] = cursor.fetchone()[0] is not None

    return statuses
