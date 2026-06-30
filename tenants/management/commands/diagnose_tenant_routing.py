from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from tenants.models import Domain, State


DEFAULT_TABLES = (
    "core_user",
    "core_patientprofile",
    "facilities_facility",
    "appointments_appointment",
    "appointments_vitals",
    "immunization_immunizationrecord",
)


class Command(BaseCommand):
    help = "Diagnoses hostname routing and tenant table availability for production errors."

    def add_arguments(self, parser):
        parser.add_argument(
            "--domain",
            required=True,
            help="Hostname to inspect, for example primary-health-care-api.vercel.app.",
        )
        parser.add_argument(
            "--schema",
            help="Expected tenant schema. If omitted, the schema routed from --domain is used.",
        )
        parser.add_argument(
            "--table",
            action="append",
            dest="tables",
            help="Table to inspect. Can be passed more than once.",
        )

    def handle(self, *args, **options):
        hostname = options["domain"].strip().lower().rstrip("/")
        expected_schema = options.get("schema")
        tables = options.get("tables") or DEFAULT_TABLES

        if "://" in hostname or "/" in hostname:
            raise CommandError("Pass only the hostname, without protocol or path.")

        self.print_database_context()
        routed_schema = self.print_domain_route(hostname)

        schema_name = (expected_schema or routed_schema or "").strip()
        if not schema_name:
            raise CommandError(
                "No tenant schema could be inferred. Register the hostname with "
                "`python manage.py route_domain <hostname> <schema_name>`."
            )

        self.print_schema_summary(schema_name)
        self.print_table_summary(schema_name, tables)

    def print_database_context(self):
        with connection.cursor() as cursor:
            cursor.execute("select current_database(), current_schema(), current_setting('search_path')")
            database_name, current_schema, search_path = cursor.fetchone()

        self.stdout.write(f"Database: {database_name}")
        self.stdout.write(f"Current schema: {current_schema}")
        self.stdout.write(f"Search path: {search_path}")

    def print_domain_route(self, hostname):
        try:
            domain = Domain.objects.select_related("tenant").get(domain=hostname)
        except Domain.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Domain '{hostname}' is not registered."))
            return None

        schema_name = domain.tenant.schema_name
        primary_text = "primary" if domain.is_primary else "secondary"
        self.stdout.write(
            self.style.SUCCESS(
                f"Domain '{hostname}' routes to schema '{schema_name}' as {primary_text}."
            )
        )
        return schema_name

    def print_schema_summary(self, schema_name):
        tenant_exists = State.objects.filter(schema_name=schema_name).exists()
        self.stdout.write(f"Tenant row for '{schema_name}': {'found' if tenant_exists else 'missing'}")

        with connection.cursor() as cursor:
            cursor.execute(
                "select schema_name from information_schema.schemata where schema_name = %s",
                [schema_name],
            )
            schema_exists = cursor.fetchone() is not None

        self.stdout.write(f"Postgres schema '{schema_name}': {'found' if schema_exists else 'missing'}")

    def print_table_summary(self, schema_name, tables):
        schemas = ("public", schema_name)
        with connection.cursor() as cursor:
            for table in tables:
                for current_schema in schemas:
                    qualified_table = f"{current_schema}.{table}"
                    cursor.execute("select to_regclass(%s)", [qualified_table])
                    exists = cursor.fetchone()[0] is not None
                    style = self.style.SUCCESS if exists else self.style.ERROR
                    self.stdout.write(style(f"{qualified_table}: {'found' if exists else 'missing'}"))

            migrations_table = f"{schema_name}.django_migrations"
            cursor.execute("select to_regclass(%s)", [migrations_table])
            if cursor.fetchone()[0] is None:
                self.stdout.write(self.style.ERROR(f"{migrations_table}: missing"))
                return

            quoted_schema = connection.ops.quote_name(schema_name)
            cursor.execute(
                f"""
                select app, name
                from {quoted_schema}.django_migrations
                where app in ('core', 'facilities', 'appointments', 'immunization')
                order by app, name
                """
            )
            migrations = cursor.fetchall()

        if migrations:
            self.stdout.write("Applied tenant migrations:")
            for app, name in migrations:
                self.stdout.write(f"  {app}.{name}")
        else:
            self.stdout.write(self.style.ERROR("No core/facilities/appointments/immunization migrations found."))
