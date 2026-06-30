from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tenants.models import Domain, State


class Command(BaseCommand):
    help = "Migrates a tenant schema, optionally routes a domain to it, then validates tenant tables."

    def add_arguments(self, parser):
        parser.add_argument("schema_name", help="Tenant schema name, for example plateau.")
        parser.add_argument(
            "--domain",
            help="Optional hostname to route to this tenant, for example primary-health-care-api.vercel.app.",
        )
        parser.add_argument(
            "--secondary",
            action="store_true",
            help="Create or update the domain as non-primary for the tenant.",
        )
        parser.add_argument(
            "--skip-migrate",
            action="store_true",
            help="Only route and validate; do not run tenant migrations.",
        )

    def handle(self, *args, **options):
        schema_name = options["schema_name"].strip()
        domain = options.get("domain")
        skip_migrate = options["skip_migrate"]

        try:
            tenant = State.objects.get(schema_name=schema_name)
        except State.DoesNotExist as exc:
            raise CommandError(f"Tenant schema '{schema_name}' does not exist.") from exc

        if not skip_migrate:
            self.stdout.write(f"Running tenant migrations for schema '{schema_name}'...")
            call_command(
                "migrate_schemas",
                "--tenant",
                "-s",
                schema_name,
                interactive=False,
                verbosity=options["verbosity"],
            )

        if domain:
            self.route_domain(domain, tenant, options["secondary"])

        check_args = [schema_name]
        if domain:
            check_args.extend(["--domain", domain])

        call_command("check_tenant_schema", *check_args, verbosity=options["verbosity"])

        self.stdout.write(
            self.style.SUCCESS(f"Tenant schema '{schema_name}' is migrated and ready.")
        )

    def route_domain(self, domain, tenant, secondary):
        hostname = domain.strip().lower().rstrip("/")

        if "://" in hostname or "/" in hostname:
            raise CommandError("Pass only the hostname, without protocol or path.")

        with transaction.atomic():
            domain_obj, created = Domain.objects.update_or_create(
                domain=hostname,
                defaults={
                    "tenant": tenant,
                    "is_primary": not secondary,
                },
            )

        action = "Created" if created else "Updated"
        primary_text = "primary" if domain_obj.is_primary else "secondary"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} {primary_text} domain '{hostname}' -> schema '{tenant.schema_name}'."
            )
        )
