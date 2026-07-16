from django.db import models, transaction, connection
from core.models import BaseModel, User

class HealthPromotion(BaseModel):
    TYPE_CHOICES = (
        ('AWARENESS', 'Awareness'),
        ('VACCINATION_DRIVE', 'Vaccination Drive'),
        ('SCREENING', 'Screening'),
        ('EDUCATION', 'Education')
    )

    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('SCHEDULED', 'Scheduled'),
        ('IN_PROCESS', 'In-Process'),
        ('CANCELLED', 'Cancelled'),
        ('COMPLETED', 'Completed')
    )

    promotion_id = models.CharField(max_length=50, unique=True, editable=False)
    sequence_number = models.BigIntegerField(null=True, blank=True, editable=False, db_index=True)
    
    title = models.CharField(max_length=255, blank=True, null=True)
    type = models.CharField(max_length=30, choices=TYPE_CHOICES, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    target_audience = models.CharField(max_length=255, blank=True, null=True)
    expected_participants = models.PositiveIntegerField(blank=True, null=True)
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)
    
    assigned_to = models.ManyToManyField(User, related_name='assigned_health_promotions', limit_choices_to={'role__in': ['CHEW', 'NURSE', 'DOCTOR']}, blank=True)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    def save(self, *args, **kwargs):
        if not self.promotion_id:
            with transaction.atomic():
                last_promo = HealthPromotion.objects.select_for_update().order_by('-sequence_number').first()
                self.sequence_number = (last_promo.sequence_number + 1) if last_promo else 1
                state_code = connection.schema_name.upper()[:3] if connection.schema_name else 'UNK'
                self.promotion_id = f"HPM-{state_code}-{self.sequence_number:06d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.promotion_id} - {self.title}"

class PostActivity(BaseModel):
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected')
    )

    health_promotion = models.OneToOneField(HealthPromotion, on_delete=models.CASCADE, related_name='post_activity')
    number_of_participants = models.PositiveIntegerField(blank=True, null=True)
    male_count = models.PositiveIntegerField(blank=True, null=True)
    female_count = models.PositiveIntegerField(blank=True, null=True)
    follow_up_required = models.BooleanField(default=False)
    key_messages_delivered = models.TextField(blank=True, null=True)
    outcome_summary = models.TextField(blank=True, null=True)
    challenges = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    def __str__(self):
        return f"Post Activity for {self.health_promotion.title}"
