# referrals/models.py
from django.db import models, transaction, connection
from core.models import BaseModel, User
from appointments.models import Appointment
from facilities.models import Facility
from departments.models import Department

class Referral(BaseModel):
    TYPE_CHOICES = (
        ('PHYSICAL', 'Physical'),
        ('TELEMEDICINE', 'Telemedicine'),
        ('EMERGENCY', 'Emergency')
    )
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('ACCEPTED', 'Accepted'),
        ('REJECTED', 'Rejected')
    )
    DESTINATION_LEVEL_CHOICES = (
        ('PRIMARY', 'Primary Health Care (Internal)'),
        ('SECONDARY', 'Secondary Health Care'),
        ('HIGHER', 'Higher Health Care'),
        ('OTHER', 'Other')
    )
    TRANSPORT_MODE_CHOICES = (
        ('PRIVATE', 'Private Vehicle'),
        ('AMBULANCE', 'Ambulance'),
        ('PUBLIC', 'Public Transportation'),
        ('OTHER', 'Other')
    )
    REFERRAL_MODE_CHOICES = (
        ('SOFTCOPY', 'Softcopy (Email/Digital)'),
        ('HARDCOPY', 'Hardcopy (Physical Document)')
    )

    referral_id = models.CharField(max_length=50, unique=True, editable=False)
    sequence_number = models.BigIntegerField(null=True, blank=True, editable=False, db_index=True)

    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='referrals')
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='all_referrals', limit_choices_to={'role': 'PATIENT'})
    referring_facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name='outbound_referrals')
    referred_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='authored_referrals', help_text="Staff who initiated this")
    
    destination_level = models.CharField(max_length=20, choices=DESTINATION_LEVEL_CHOICES, default='PRIMARY')
    receiving_facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name='inbound_referrals', null=True, blank=True)
    receiving_department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='inbound_referrals')

    referral_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='PHYSICAL')
    mode_of_transportation = models.CharField(max_length=20, choices=TRANSPORT_MODE_CHOICES, null=True, blank=True)
    reason_for_referral = models.TextField()
    clinical_summary = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    mode_of_referral = models.CharField(max_length=20, choices=REFERRAL_MODE_CHOICES, null=True, blank=True)
    target_doctor_email = models.EmailField(null=True, blank=True)
    target_department_email = models.EmailField(null=True, blank=True)
    email_subject = models.CharField(max_length=255, null=True, blank=True)
    email_body = models.TextField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.referral_id:
            with transaction.atomic():
                last_ref = Referral.objects.select_for_update().order_by('-sequence_number').first()
                self.sequence_number = (last_ref.sequence_number + 1) if last_ref else 1
                state_code = connection.schema_name.upper()[:3] if connection.schema_name else 'UNK'
                self.referral_id = f"REF-{state_code}-{self.sequence_number:06d}"
        super().save(*args, **kwargs)

    def __str__(self):
        dest = self.receiving_facility.name if self.receiving_facility else self.get_destination_level_display()
        return f"{self.referral_id}: {self.referring_facility.name} -> {dest}"
