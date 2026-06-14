from django.db import models
from core.models import BaseModel, User
from appointments.models import Appointment
from inventory.models import InventoryItem
from django.utils import timezone

class ImmunizationRecord(BaseModel):
    SESSION_TYPES = (
        ('FIXED', 'Fixed (In-Facility)'),
        ('OUTREACH', 'Outreach'),
        ('MOBILE', 'Mobile')
    )
    STATUS_CHOICES = (
        ('COMPLETED', 'Completed'),
        ('PENDING', 'Pending'),
        ('MISSED', 'Missed')
    )

    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='immunizations', limit_choices_to={'role': 'PATIENT'})
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='immunization_records')
    facility = models.ForeignKey('facilities.Facility', on_delete=models.CASCADE, related_name='immunizations')
    administered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='administered_vaccines')
    session_type = models.CharField(max_length=20, choices=SESSION_TYPES, default='FIXED')
    state = models.CharField(max_length=100)
    lga = models.CharField(max_length=100)
    ward = models.CharField(max_length=100)
    site_name = models.CharField(max_length=255, blank=True, null=True, help_text="Required for Outreach/Mobile")
    
    vaccine_given = models.ForeignKey(
        InventoryItem, 
        on_delete=models.PROTECT, 
        related_name='vaccinations',
        limit_choices_to={'drug_classification': 'IMMUNIZATION'}
    )
    
    dose_number = models.PositiveIntegerField(default=1, help_text="Which dose in the sequence this was.")
    next_due_date = models.DateField(null=True, blank=True, help_text="Calculated automatically by the ScheduleEngine")
    date_of_visit = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='COMPLETED')
    age_at_vaccination = models.CharField(max_length=50, blank=True, null=True)
    reporting_month = models.IntegerField(editable=False)
    reporting_year = models.IntegerField(editable=False)
    
    notes = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.date_of_visit:
            self.reporting_month = self.date_of_visit.month
            self.reporting_year = self.date_of_visit.year

        if not self.age_at_vaccination and getattr(self, 'patient', None) and hasattr(self.patient, 'patient_profile'):
            dob = self.patient.patient_profile.date_of_birth
            if dob:
                delta_days = (self.date_of_visit - dob).days
                if delta_days < 30:
                    self.age_at_vaccination = f"{delta_days // 7} Weeks" if delta_days >= 7 else f"{delta_days} Days"
                elif delta_days < 365:
                    self.age_at_vaccination = f"{delta_days // 30} Months"
                else:
                    self.age_at_vaccination = f"{delta_days // 365} Years"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.vaccine_given.name} (Dose {self.dose_number}) for {self.patient.first_name}"
