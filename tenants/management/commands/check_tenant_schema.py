from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from tenants.models import Domain, State


class Command(BaseCommand):
    help = "Checks tenant domain routing and required tenant tables."

    def add_arguments(self, parser):
        parser.add_argument(
            "schema_name",
            nargs="?",
            help="Tenant schema name, for example plateau.",
        )
        parser.add_argument(
            "--all-tenants",
            action="store_true",
            help="Check every non-public tenant schema.",
        )
        parser.add_argument(
            "--domain",
            help="Optional hostname that should route to this tenant schema.",
        )
        parser.add_argument(
            "--table",
            action="append",
            dest="tables",
            help=(
                "Required table to check. Can be passed more than once. "
                "By default, every managed table from TENANT_APPS is checked."
            ),
        )

    def handle(self, *args, **options):
        schema_name = options.get("schema_name")
        check_all_tenants = options["all_tenants"]
        domain = options.get("domain")
        tables = options.get("tables") or self.get_expected_tenant_tables()

        if check_all_tenants and schema_name:
            raise CommandError("Pass either a schema_name or --all-tenants, not both.")

        if check_all_tenants and domain:
            raise CommandError("--domain can only be used when checking one schema.")

        if not check_all_tenants and not schema_name:
            raise CommandError("Pass a schema_name or use --all-tenants.")

        if check_all_tenants:
            schema_names = list(
                State.objects.exclude(schema_name="public")
                .order_by("schema_name")
                .values_list("schema_name", flat=True)
            )
            if not schema_names:
                raise CommandError("No non-public tenant schemas exist.")
        else:
            schema_name = schema_name.strip()
            if not State.objects.filter(schema_name=schema_name).exists():
                raise CommandError(f"Tenant schema '{schema_name}' does not exist.")
            schema_names = [schema_name]
            self.check_domain(domain, schema_name)

        missing_tables = []
        for current_schema in schema_names:
            missing_tables.extend(self.check_schema_tables(current_schema, tables))

        if missing_tables:
            schemas = ", ".join(sorted({table.split(".", 1)[0] for table in missing_tables}))
            raise CommandError(
                "Missing required tenant tables. Run "
                f"`python manage.py migrate_schemas --tenant -s <schema_name>` for: {schemas}. "
                "against the same database."
            )

    def get_expected_tenant_tables(self):
        tenant_app_names = set(settings.TENANT_APPS)
        tenant_app_labels = {
            app_config.label
            for app_config in apps.get_app_configs()
            if app_config.name in tenant_app_names
        }

        tables = {
            model._meta.db_table
            for model in apps.get_models(include_auto_created=True)
            if model._meta.app_label in tenant_app_labels
            and model._meta.managed
            and not model._meta.proxy
        }

        return sorted(tables)

    def check_domain(self, domain, schema_name):
        if not domain:
            return

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

    def check_schema_tables(self, schema_name, tables):
        self.stdout.write(f"Checking {len(tables)} tenant tables in schema '{schema_name}'...")

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

        return missing_tables
