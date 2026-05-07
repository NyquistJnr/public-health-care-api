# prescriptions/models.py
from django.db import models, transaction, connection
from core.models import BaseModel, User
from appointments.models import Appointment
from inventory.models import Drug

class Prescription(BaseModel):
    PRIORITY_CHOICES = (
        ('NORMAL', 'Normal'),
        ('URGENT', 'Urgent'),
        ('STAT', 'STAT / Immediate')
    )
    STATUS_CHOICES = (
        ('PENDING', 'Pending (Not Dispensed)'),
        ('PARTIAL', 'Partially Dispensed'),
        ('DISPENSED', 'Fully Dispensed'),
        ('CANCELLED', 'Cancelled')
    )

    prescription_id = models.CharField(max_length=50, unique=True, editable=False)
    sequence_number = models.BigIntegerField(null=True, blank=True, editable=False, db_index=True)
    
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='prescriptions', limit_choices_to={'role': 'PATIENT'})
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='prescriptions')
    prescribed_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='authored_prescriptions')
    
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='NORMAL')
    instructions = models.TextField(blank=True, null=True, help_text="General instructions for the pharmacist or patient")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    def save(self, *args, **kwargs):
        if not self.prescription_id:
            with transaction.atomic():
                last_rx = Prescription.objects.select_for_update().order_by('-sequence_number').first()
                self.sequence_number = (last_rx.sequence_number + 1) if last_rx else 1
                state_code = connection.schema_name.upper()[:3] if connection.schema_name else 'UNK'
                self.prescription_id = f"RX-{state_code}-{self.sequence_number:06d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.prescription_id} for {self.patient.first_name}"


class PrescriptionItem(BaseModel):
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name='items')
    drug = models.ForeignKey(Drug, on_delete=models.SET_NULL, null=True, blank=True, related_name='prescription_items')
    custom_drug_name = models.CharField(max_length=255, blank=True, null=True, help_text="Used only if the drug is not in inventory")
    dosage = models.CharField(max_length=100, help_text="e.g., 500mg, 10ml")
    frequency = models.CharField(max_length=100, help_text="e.g., BD (Twice daily), TDS (Thrice daily)")
    duration = models.CharField(max_length=100, help_text="e.g., 5 Days, 1 Month")

    def get_medication_name(self):
        """Returns the actual inventory drug name, or the custom text if it's external."""
        if self.drug:
            return self.drug.name
        return self.custom_drug_name

    def __str__(self):
        return f"{self.get_medication_name()} - {self.dosage} ({self.prescription.prescription_id})"
