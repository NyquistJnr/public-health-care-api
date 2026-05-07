# consultations/models.py
from django.db import models, transaction, connection
from core.models import BaseModel, User
from appointments.models import Appointment

class Consultation(BaseModel):
    consultation_id = models.CharField(max_length=50, unique=True, editable=False)
    sequence_number = models.BigIntegerField(null=True, blank=True, editable=False, db_index=True)
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='consultation')
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='consultation_records', limit_choices_to={'role': 'PATIENT'})
    doctor = models.ForeignKey(User, on_delete=models.PROTECT, related_name='conducted_consultations')
    chief_complaint = models.TextField()
    presenting_complaint = models.TextField()
    history_of_present_complaint = models.TextField(blank=True, null=True)
    past_medical_history = models.TextField(blank=True, null=True)
    examination_findings = models.TextField(blank=True, null=True)
    primary_diagnosis = models.CharField(max_length=255)
    secondary_diagnosis = models.CharField(max_length=255, blank=True, null=True)
    treatment_plan = models.TextField()
    additional_notes = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.consultation_id:
            with transaction.atomic():
                last_record = Consultation.objects.select_for_update().order_by('-sequence_number').first()
                self.sequence_number = (last_record.sequence_number + 1) if last_record else 1
                state_code = connection.schema_name.upper()[:3] if connection.schema_name else 'UNK'
                self.consultation_id = f"CON-{state_code}-{self.sequence_number:06d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.consultation_id} - {self.patient.first_name}"
