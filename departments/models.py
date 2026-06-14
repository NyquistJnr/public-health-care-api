# departments/models.py

from django.db import models
from django.db.models import Q
from core.models import BaseModel, User
from facilities.models import Facility

class Department(BaseModel):
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=255, help_text="e.g., Outpatient (OPD), Maternity, Pharmacy, Laboratory")
    description = models.TextField(blank=True, null=True)
    
    head = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='headed_departments',
        limit_choices_to=~Q(role='PATIENT'),
        help_text="The staff member managing this department."
    )
    
    members = models.ManyToManyField(
        User, 
        related_name='department_memberships', 
        limit_choices_to=~Q(role='PATIENT'),
        blank=True
    )

    def __str__(self):
        return f"{self.name} - {self.facility.name}"
