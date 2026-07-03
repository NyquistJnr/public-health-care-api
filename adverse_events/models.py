# adverse_events/models.py
from django.db import models, transaction, connection
from core.models import BaseModel, User
from inventory.models import InventoryItem


class AdverseEvent(BaseModel):
    SEVERITY_CHOICES = (
        ('MILD', 'Mild'),
        ('MODERATE', 'Moderate'),
        ('SEVERE', 'Severe'),
        ('LIFE_THREATENING', 'Life-Threatening'),
        ('FATAL', 'Fatal'),
    )

    STATUS_CHOICES = (
        ('REPORTED', 'Reported'),
        ('UNDER_REVIEW', 'Under Review'),
        ('RESOLVED', 'Resolved'),
        ('CLOSED', 'Closed'),
    )

    event_id = models.CharField(max_length=50, unique=True, editable=False)
    sequence_number = models.BigIntegerField(null=True, blank=True, editable=False, db_index=True)

    patient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='adverse_events',
        limit_choices_to={'role': 'PATIENT'}
    )
    reported_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reported_adverse_events',
        help_text="Staff member reporting the event. Defaults to the submitting user."
    )
    suspected_drug = models.ForeignKey(
        InventoryItem, on_delete=models.PROTECT, related_name='adverse_events',
        limit_choices_to={'inventory_category': 'DRUG'}
    )

    dosage = models.CharField(max_length=100, help_text="e.g., 500mg BD")
    date_of_reaction = models.DateField()
    stop_date = models.DateField(null=True, blank=True, help_text="Date the suspected drug was stopped, if applicable")
    reaction_type = models.CharField(max_length=255, help_text="e.g., Rash, Anaphylaxis, Nausea")
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    detailed_symptoms = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='REPORTED')

    def save(self, *args, **kwargs):
        if not self.event_id:
            with transaction.atomic():
                last_event = AdverseEvent.objects.select_for_update().order_by('-sequence_number').first()
                self.sequence_number = (last_event.sequence_number + 1) if last_event else 1
                state_code = connection.schema_name.upper()[:3] if connection.schema_name else 'UNK'
                self.event_id = f"ADR-{state_code}-{self.sequence_number:06d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.event_id} - {self.patient.first_name} {self.patient.last_name} ({self.get_severity_display()})"
