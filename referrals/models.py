# referrals/models.py
from django.db import models, transaction, connection
from core.models import BaseModel, User
from appointments.models import Appointment
from facilities.models import Facility

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

    referral_id = models.CharField(max_length=50, unique=True, editable=False)
    sequence_number = models.BigIntegerField(null=True, blank=True, editable=False, db_index=True)

    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='referrals')
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='all_referrals', limit_choices_to={'role': 'PATIENT'})
    
    referring_facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name='outbound_referrals')
    receiving_facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name='inbound_referrals')
    
    referred_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='authored_referrals', help_text="Staff who initiated this")
    
    referral_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='PHYSICAL')
    reason_for_referral = models.TextField()
    clinical_summary = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    def save(self, *args, **kwargs):
        if not self.referral_id:
            with transaction.atomic():
                last_ref = Referral.objects.select_for_update().order_by('-sequence_number').first()
                self.sequence_number = (last_ref.sequence_number + 1) if last_ref else 1
                state_code = connection.schema_name.upper()[:3] if connection.schema_name else 'UNK'
                self.referral_id = f"REF-{state_code}-{self.sequence_number:06d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.referral_id}: {self.referring_facility.name} -> {self.receiving_facility.name}"
