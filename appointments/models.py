from django.db import models, transaction, connection
from core.models import BaseModel, User
from django.utils import timezone
from django.core.validators import RegexValidator

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



##### Vitals #####

class Vitals(BaseModel):
    vital_id = models.CharField(max_length=50, unique=True, editable=False)
    sequence_number = models.BigIntegerField(null=True, blank=True, editable=False, db_index=True)
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vitals', limit_choices_to={'role': 'PATIENT'})
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='vitals')
    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text="Celsius (°C)")
    bp_validator = RegexValidator(regex=r'^\d{2,3}/\d{2,3}$', message="BP must be in format Systolic/Diastolic (e.g., 120/80)")
    blood_pressure = models.CharField(max_length=7, validators=[bp_validator], null=True, blank=True)
    
    pulse_rate = models.PositiveIntegerField(null=True, blank=True, help_text="BPM")
    respiratory_rate = models.PositiveIntegerField(null=True, blank=True, help_text="Breaths per minute")
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    height_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    spo2 = models.PositiveIntegerField(null=True, blank=True, help_text="Oxygen saturation %")
    
    notes = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.vital_id:
            with transaction.atomic():
                last_vital = Vitals.objects.select_for_update().order_by('-sequence_number').first()
                self.sequence_number = (last_vital.sequence_number + 1) if last_vital else 1
                state_code = connection.schema_name.upper()[:3] if connection.schema_name else 'UNK'
                self.vital_id = f"VIT-{state_code}-{self.sequence_number:06d}"
                
        if self.appointment and not getattr(self, 'patient', None):
            self.patient = self.appointment.patient
            
        super().save(*args, **kwargs)

    @property
    def bmi(self):
        """Auto-calculate BMI: Weight (kg) / Height (m)^2"""
        if self.weight_kg and self.height_cm and self.height_cm > 0:
            height_m = float(self.height_cm) / 100.0
            bmi_val = float(self.weight_kg) / (height_m ** 2)
            return round(bmi_val, 2)
        return None

    @property
    def age_at_visit(self):
        """Calculates exact age based on DOB and the date the vitals were recorded."""
        try:
            dob = self.patient.patient_profile.date_of_birth
            record_date = self.created_at.date() if self.created_at else timezone.now().date()
            if dob:
                return record_date.year - dob.year - ((record_date.month, record_date.day) < (dob.month, dob.day))
        except AttributeError:
            pass
        return None

    def __str__(self):
        return f"{self.vital_id} for {self.patient.first_name} on {self.created_at.strftime('%Y-%m-%d')}"
