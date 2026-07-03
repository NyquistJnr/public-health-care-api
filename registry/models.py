# registry/models.py
import uuid

from django.db import models

SINGLETON_THRESHOLD_ID = uuid.UUID('00000000-0000-0000-0000-000000000001')


class Disease(models.Model):
    """Global disease/condition registry. Lives in the public schema (SHARED_APPS) - identical for every state."""

    SEVERITY_CHOICES = (
        ('CRITICAL', 'Critical / Dangerous'),
        ('MODERATE', 'Moderate'),
        ('LOW', 'Low'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, db_index=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_severity_display()})"


class SystemThreshold(models.Model):
    """
    Singleton config row (single global set of values, shared across every state).
    Use SystemThreshold.get_solo() rather than querying directly.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    disease_compliance_threshold_percent = models.PositiveIntegerField(
        default=50, help_text="Reporting Compliance Alert Threshold (Diseases), as a percentage."
    )
    failed_login_attempts_threshold = models.PositiveIntegerField(
        default=8, help_text="Failed Login Attempts Threshold."
    )
    system_error_threshold = models.PositiveIntegerField(
        default=50, help_text="System Error Threshold, count of errors."
    )
    inactive_facility_threshold_days = models.PositiveIntegerField(
        default=7, help_text="Inactive Facility Alert Threshold, in days."
    )
    high_usage_threshold_users = models.PositiveIntegerField(
        default=200, help_text="High System Usage Alert Threshold, count of active users."
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "System Thresholds"

    def save(self, *args, **kwargs):
        self.pk = SINGLETON_THRESHOLD_ID
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=SINGLETON_THRESHOLD_ID)
        return obj
