# laboratory/models.py
from django.db import models, transaction, connection
from django.utils import timezone
from core.models import BaseModel, User
from appointments.models import Appointment

class LabRequest(BaseModel):
    PRIORITY_CHOICES = (
        ('NORMAL', 'Normal'),
        ('URGENT', 'Urgent'),
        ('STAT', 'STAT / Emergency')
    )
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PARTIAL', 'Partially Completed'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled')
    )

    request_id = models.CharField(max_length=50, unique=True, editable=False)
    sequence_number = models.BigIntegerField(null=True, blank=True, editable=False, db_index=True)
    
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='lab_requests', limit_choices_to={'role': 'PATIENT'})
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='lab_requests')
    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='recorded_lab_requests')
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='ordered_lab_requests')
    
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='NORMAL')
    clinical_notes = models.TextField(blank=True, null=True, help_text="Reason for the tests")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    def save(self, *args, **kwargs):
        if not self.request_id:
            with transaction.atomic():
                last_req = LabRequest.objects.select_for_update().order_by('-sequence_number').first()
                self.sequence_number = (last_req.sequence_number + 1) if last_req else 1
                state_code = connection.schema_name.upper()[:3] if connection.schema_name else 'UNK'
                self.request_id = f"LAB-{state_code}-{self.sequence_number:06d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.request_id} for {self.patient.first_name}"


class LabTest(BaseModel):
    TEST_STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('SAMPLE_COLLECTED', 'Sample Collected'),
        ('PROCESSING', 'Processing'),
        ('RESULT_READY', 'Result Ready'),
        ('CANCELLED', 'Cancelled')
    )

    lab_request = models.ForeignKey(LabRequest, on_delete=models.CASCADE, related_name='tests')
    test_name = models.CharField(max_length=255)
    sample_type = models.CharField(max_length=100, blank=True, null=True, help_text="e.g., Blood, Urine, Swab")
    test_status = models.CharField(max_length=30, choices=TEST_STATUS_CHOICES, default='PENDING')
    result_value = models.CharField(max_length=255, blank=True, null=True)
    result_unit = models.CharField(max_length=50, blank=True, null=True)
    test_method = models.CharField(max_length=100, blank=True, null=True, help_text="e.g., Microscopy, RDT")
    result_interpretation = models.TextField(blank=True, null=True, help_text="e.g., High, Normal, Abnormal")
    result_notes = models.TextField(blank=True, null=True)
    
    result_entered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='entered_lab_results')
    result_date = models.DateTimeField(null=True, blank=True)

    def check_and_update_parent_status(self):
        """Automatically upgrades the parent LabRequest status based on sibling tests"""
        siblings = self.lab_request.tests.exclude(test_status='CANCELLED')
        total = siblings.count()
        completed = siblings.filter(test_status='RESULT_READY').count()

        if total > 0:
            if completed == total:
                self.lab_request.status = 'COMPLETED'
            elif completed > 0:
                self.lab_request.status = 'PARTIAL'
            else:
                self.lab_request.status = 'PENDING'
            self.lab_request.save(update_fields=['status', 'updated_at'])

    def __str__(self):
        return f"{self.test_name} ({self.test_status})"
