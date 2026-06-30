from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tenants.models import Domain, State


class Command(BaseCommand):
    help = "Routes a hostname to a tenant schema."

    def add_arguments(self, parser):
        parser.add_argument("domain", help="Hostname to route, for example primary-health-care-api.vercel.app")
        parser.add_argument("schema_name", help="Tenant schema name, for example plateau")
        parser.add_argument(
            "--secondary",
            action="store_true",
            help="Create the domain as non-primary for the tenant.",
        )

    def handle(self, *args, **options):
        domain = options["domain"].strip().lower().rstrip("/")
        schema_name = options["schema_name"].strip()

        if "://" in domain or "/" in domain:
            raise CommandError("Pass only the hostname, without protocol or path.")

        try:
            tenant = State.objects.get(schema_name=schema_name)
        except State.DoesNotExist as exc:
            raise CommandError(f"Tenant schema '{schema_name}' does not exist.") from exc

        with transaction.atomic():
            domain_obj, created = Domain.objects.update_or_create(
                domain=domain,
                defaults={
                    "tenant": tenant,
                    "is_primary": not options["secondary"],
                },
            )

        action = "Created" if created else "Updated"
        primary_text = "primary" if domain_obj.is_primary else "secondary"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} {primary_text} domain '{domain}' -> schema '{tenant.schema_name}'."
            )
        )
