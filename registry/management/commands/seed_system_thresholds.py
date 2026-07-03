# registry/management/commands/seed_system_thresholds.py
from django.core.management.base import BaseCommand

from registry.models import SystemThreshold


class Command(BaseCommand):
    help = "Creates the global SystemThreshold singleton row with default values if it doesn't already exist."

    def handle(self, *args, **kwargs):
        existed = SystemThreshold.objects.exists()
        threshold = SystemThreshold.get_solo()

        if existed:
            self.stdout.write(self.style.WARNING("SystemThreshold already exists. Skipping."))
        else:
            self.stdout.write(self.style.SUCCESS(f"SystemThreshold created with defaults: {threshold!r}"))
