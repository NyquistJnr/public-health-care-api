# core/models.py
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    ROLE_CHOICES = (
        ('ADMIN', 'State Admin'),
        ('DOCTOR', 'Doctor'),
        ('NURSE', 'Nurse'),
        ('PATIENT', 'Patient'),
    )
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='PATIENT')

    # We can add healthcare-specific fields later, such as:
    # phone_number = models.CharField(max_length=15, blank=True)
    # medical_id = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        return f"{self.email} - {self.get_role_display()}"
