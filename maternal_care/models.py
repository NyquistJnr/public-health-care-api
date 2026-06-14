# maternal_care/models.py
from django.db import models, transaction, connection
from datetime import timedelta
from core.models import BaseModel, User
from appointments.models import Appointment

class MaternalScheduleRule(BaseModel):
    """Global (State-Level) Schedule Settings for ANC/PNC"""
    CARE_TYPES = (
        ('ANC', 'Antenatal Care'),
        ('PNC', 'Postnatal Care')
    )
    RULE_TYPES = (
        ('ONCE', 'Once'),
        ('RECURRING', 'Recurring (Fixed Interval)'),
        ('VARIABLE_SEQUENCE', 'Variable Sequence')
    )

    care_type = models.CharField(max_length=10, choices=CARE_TYPES, unique=True, help_text="One active rule per care type.")
    rule_type = models.CharField(max_length=20, choices=RULE_TYPES, default='VARIABLE_SEQUENCE')
    
    interval_days = models.PositiveIntegerField(default=0, help_text="Used if RECURRING (e.g., every 30 days)")
    intervals_sequence = models.JSONField(
        default=list, blank=True, 
        help_text="Used if VARIABLE. Array of days between visits. e.g., [28, 28, 14, 14, 7]"
    )
    visit_tasks = models.JSONField(
        default=dict, blank=True, 
        help_text="Map of visit sequence index to list of tasks. e.g., {'0': ['Booking Bloods', 'Dating Scan'], '4': ['Anomaly Scan']}"
    )

    def __str__(self):
        return f"{self.get_care_type_display()} Global Schedule Rule"


class MaternalCareEpisode(BaseModel):
    STATUS_CHOICES = (
        ('ACTIVE', 'Active (Pregnant)'),
        ('DELIVERED', 'Delivered'),
        ('CLOSED', 'Closed / Postpartum Complete'),
        ('MISCARRIAGE', 'Miscarriage / Loss')
    )
    
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pregnancies', limit_choices_to={'role': 'PATIENT'})
    episode_id = models.CharField(max_length=50, unique=True, editable=False)
    sequence_number = models.BigIntegerField(null=True, blank=True, editable=False, db_index=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    last_menstrual_period = models.DateField(null=True, blank=True)
    expected_date_of_delivery = models.DateField(null=True, blank=True)
    
    gravida = models.PositiveIntegerField(default=1, help_text="Total number of pregnancies")
    parity = models.PositiveIntegerField(default=0, help_text="Number of previous births")
    living_children = models.PositiveIntegerField(default=0)
    
    partner_name = models.CharField(max_length=255, blank=True, null=True)
    partner_phone = models.CharField(max_length=20, blank=True, null=True)

    custom_anc_schedule = models.JSONField(
        blank=True, null=True, 
        help_text="Overrides the Global ANC rule. Format: {'rule_type': '...', 'intervals_sequence': [], 'visit_tasks': {}}"
    )
    custom_pnc_schedule = models.JSONField(
        blank=True, null=True, 
        help_text="Overrides the Global PNC rule. Same format."
    )

    def save(self, *args, **kwargs):
        if self.last_menstrual_period and not self.expected_date_of_delivery:
            self.expected_date_of_delivery = self.last_menstrual_period + timedelta(days=280)

        if not self.episode_id:
            with transaction.atomic():
                last_ep = MaternalCareEpisode.objects.select_for_update().order_by('-sequence_number').first()
                self.sequence_number = (last_ep.sequence_number + 1) if last_ep else 1
                state_code = connection.schema_name.upper()[:3] if connection.schema_name else 'UNK'
                self.episode_id = f"MAT-{state_code}-{self.sequence_number:06d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.episode_id} - {self.patient.first_name} ({self.get_status_display()})"


class ANCVisit(BaseModel):
    ATTENDANCE_CHOICES = (('NEW', 'New'), ('RETURN', 'Return'))
    
    episode = models.ForeignKey(MaternalCareEpisode, on_delete=models.CASCADE, related_name='anc_visits')
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='anc_record')
    attendance_type = models.CharField(max_length=10, choices=ATTENDANCE_CHOICES, default='NEW')
    
    visit_sequence_number = models.PositiveIntegerField(default=1, help_text="Which visit in the sequence is this?")
    next_visit_date = models.DateField(null=True, blank=True, help_text="Calculated date for the next visit")
    recommended_tasks = models.JSONField(default=list, blank=True, help_text="Tasks (like Ultrasound) due for THIS visit")
    
    hiv_status = models.CharField(max_length=50, blank=True, null=True)
    vdrl_syphilis = models.CharField(max_length=50, blank=True, null=True)
    hepatitis_b = models.CharField(max_length=50, blank=True, null=True)
    hemoglobin = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="g/dL")
    urinalysis = models.TextField(blank=True, null=True)
    
    tt_dose_given = models.CharField(max_length=20, blank=True, null=True)
    iptp_dose_given = models.CharField(max_length=20, blank=True, null=True)
    iron_folate_given = models.BooleanField(default=False)
    
    risk_factors = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"ANC - {self.episode.episode_id} on {self.appointment.appointment_date}"


class PNCVisit(BaseModel):
    ATTENDANCE_CHOICES = (('NEW', 'New'), ('RETURN', 'Return'))
    OUTCOME_CHOICES = (('TREATED', 'Treated'), ('ADMITTED', 'Admitted'), ('REFERRED', 'Referred Out'))
    
    episode = models.ForeignKey(MaternalCareEpisode, on_delete=models.CASCADE, related_name='pnc_visits')
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='pnc_record')
    attendance_type = models.CharField(max_length=10, choices=ATTENDANCE_CHOICES, default='NEW')
    
    visit_sequence_number = models.PositiveIntegerField(default=1)
    next_visit_date = models.DateField(null=True, blank=True)
    recommended_tasks = models.JSONField(default=list, blank=True)

    timing_of_visit = models.CharField(max_length=50, help_text="e.g., Within 24h, 3 Days, 7 Days, 6 Weeks")
    vaginal_examination_conducted = models.BooleanField(default=False)
    hemoglobin_pcv = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    urinalysis = models.TextField(blank=True, null=True)
    counselling_topics = models.JSONField(default=list, blank=True, help_text="List of topics covered")
    outcome = models.CharField(max_length=50, choices=OUTCOME_CHOICES, default='TREATED')
    referral_reason = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"PNC - {self.episode.episode_id} on {self.appointment.appointment_date}"

class PNCNewbornAssessment(BaseModel):
    OUTCOME_CHOICES = (
        ('HEALTHY', 'Healthy / Discharged'),
        ('ADMITTED', 'Admitted to NICU'),
        ('REFERRED', 'Referred Out')
    )
    
    pnc_visit = models.ForeignKey(PNCVisit, on_delete=models.CASCADE, related_name='newborn_assessments')
    baby = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pnc_assessments', limit_choices_to={'role': 'PATIENT'})
    
    cord_care_assessed = models.BooleanField(default=False)
    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text="Celsius (°C)")
    exclusive_breastfeeding = models.CharField(max_length=50, blank=True, null=True, help_text="Yes, No, Struggling")
    
    # E.g., ["Poor sucking", "Fast breathing"]
    newborn_danger_signs = models.JSONField(default=list, blank=True)
    neonatal_jaundice = models.BooleanField(default=False)
    first_dose_antibiotics_given = models.BooleanField(default=False)
    kmc_provided = models.BooleanField(default=False)
    
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES, default='HEALTHY')

    def __str__(self):
        return f"Assessment for {self.baby.first_name} (PNC: {self.pnc_visit.id})"
