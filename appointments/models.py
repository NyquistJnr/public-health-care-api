from django.db import models, transaction, connection
from core.models import BaseModel, User
from django.utils import timezone

class Appointment(BaseModel):
    VISIT_TYPES = (
        ('GENERAL', 'General Consultation'),
        ('FOLLOW_UP', 'Follow-up'),
        ('ANTENATAL', 'Antenatal Care'),
        ('IMMUNIZATION', 'Immunization'),
        ('EMERGENCY', 'Emergency'),
        ('OTHER', 'Other')
    )
    
    STATUS_CHOICES = (
        ('SCHEDULED', 'Scheduled'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
        ('NO_SHOW', 'No Show')
    )

    facility = models.ForeignKey('facilities.Facility', on_delete=models.CASCADE, related_name='appointments')
    appointment_id = models.CharField(max_length=50, unique=True, editable=False)
    sequence_number = models.BigIntegerField(null=True, blank=True, editable=False, db_index=True)
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='appointments', limit_choices_to={'role': 'PATIENT'})
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='assigned_appointments', limit_choices_to={'role__in': ['DOCTOR', 'NURSE']})

    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    visit_type = models.CharField(max_length=20, choices=VISIT_TYPES, default='GENERAL')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SCHEDULED')

    reason_for_visit = models.TextField()
    notes = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.appointment_id:
            with transaction.atomic():
                last_apt = Appointment.objects.select_for_update().order_by('-sequence_number').first()
                self.sequence_number = (last_apt.sequence_number + 1) if last_apt else 1
                state_code = connection.schema_name.upper()[:3] if connection.schema_name else 'UNK'
                self.appointment_id = f"APT-{state_code}-{self.sequence_number:06d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.appointment_id} - {self.patient.first_name} on {self.appointment_date}"
