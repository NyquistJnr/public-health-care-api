from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from tenants.models import Domain, State


DEFAULT_TABLES = (
    "core_auditlog",
    "core_notificationreadstatus",
    "facilities_facility",
)


class Command(BaseCommand):
    help = "Checks tenant domain routing and required tenant tables."

    def add_arguments(self, parser):
        parser.add_argument("schema_name", help="Tenant schema name, for example plateau")
        parser.add_argument(
            "--domain",
            help="Optional hostname that should route to this tenant schema.",
        )
        parser.add_argument(
            "--table",
            action="append",
            dest="tables",
            help="Required table to check. Can be passed more than once.",
        )

    def handle(self, *args, **options):
        schema_name = options["schema_name"].strip()
        domain = options.get("domain")
        tables = options.get("tables") or DEFAULT_TABLES

        if not State.objects.filter(schema_name=schema_name).exists():
            raise CommandError(f"Tenant schema '{schema_name}' does not exist.")

        if domain:
            hostname = domain.strip().lower().rstrip("/")
            try:
                domain_obj = Domain.objects.select_related("tenant").get(domain=hostname)
            except Domain.DoesNotExist as exc:
                raise CommandError(f"Domain '{hostname}' is not registered.") from exc

            routed_schema = domain_obj.tenant.schema_name
            if routed_schema != schema_name:
                raise CommandError(
                    f"Domain '{hostname}' routes to '{routed_schema}', not '{schema_name}'."
                )

            self.stdout.write(self.style.SUCCESS(f"Domain '{hostname}' routes to '{schema_name}'."))

        missing_tables = []
        with connection.cursor() as cursor:
            for table in tables:
                qualified_table = f"{schema_name}.{table}"
                cursor.execute("select to_regclass(%s)", [qualified_table])
                exists = cursor.fetchone()[0] is not None
                if exists:
                    self.stdout.write(self.style.SUCCESS(f"Found {qualified_table}."))
                else:
                    missing_tables.append(qualified_table)
                    self.stdout.write(self.style.ERROR(f"Missing {qualified_table}."))

        if missing_tables:
            raise CommandError(
                "Missing required tenant tables. Run "
                f"`python manage.py migrate_schemas --tenant -s {schema_name}` "
                "against the same database."
            )
