# facilities/models.py
from django.db import models, transaction, connection
from core.models import BaseModel, User

class Facility(BaseModel):
    code = models.CharField(max_length=50, unique=True, editable=False)
    sequence_number = models.BigIntegerField(editable=False, db_index=True)
    name = models.CharField(max_length=255)
    facility_type = models.CharField(max_length=100)
    lga = models.CharField(max_length=100)
    address = models.TextField()
    level = models.CharField(max_length=100)
    manager_phone = models.CharField(max_length=20, null=True, blank=True)
    manager_email = models.EmailField(null=True, blank=True)
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_facilities')
    it_admin = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='administered_facilities')
    suspended_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.code:
            with transaction.atomic():
                last_facility = Facility.objects.select_for_update().order_by('-sequence_number').first()
                self.sequence_number = (last_facility.sequence_number + 1) if last_facility else 1
                state_code = connection.schema_name.upper()[:3] if connection.schema_name else 'UNK'
                name_clean = self.name.replace(" ", "").upper()
                lga_clean = self.lga.replace(" ", "").upper()
                
                name_part = name_clean[:3]
                lga_part = lga_clean[:3]

                if name_part == lga_part:
                    mix = name_clean[:6].ljust(6, 'X')
                else:
                    mix = f"{name_part}{lga_part}".ljust(6, 'X')

                self.code = f"PHC-{state_code}-{mix}-{self.sequence_number:06d}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.code})"
