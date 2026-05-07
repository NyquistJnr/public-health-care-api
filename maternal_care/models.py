from django.db import models, transaction, connection
from core.models import BaseModel, User
from appointments.models import Appointment

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

    def save(self, *args, **kwargs):
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
    
    # Dynamic Labs (Done during this specific visit)
    hiv_status = models.CharField(max_length=50, blank=True, null=True)
    vdrl_syphilis = models.CharField(max_length=50, blank=True, null=True)
    hepatitis_b = models.CharField(max_length=50, blank=True, null=True)
    hemoglobin = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="g/dL")
    urinalysis = models.TextField(blank=True, null=True)
    
    # Interventions
    tt_dose_given = models.CharField(max_length=20, blank=True, null=True, help_text="e.g. TT1, TT2")
    iptp_dose_given = models.CharField(max_length=20, blank=True, null=True, help_text="e.g. Dose 1, Dose 2")
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
    timing_of_visit = models.CharField(max_length=50, help_text="e.g., Within 24h, 3 Days, 7 Days, 6 Weeks")
    
    # Maternal Assessment
    vaginal_examination_conducted = models.BooleanField(default=False)
    hemoglobin_pcv = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    urinalysis = models.TextField(blank=True, null=True)
    
    # JSON array handles multiple selections easily: ["Family Planning", "Nutrition"]
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
