# core/models.py
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models, transaction, connection
from django.conf import settings
from django.utils import timezone

class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    restored_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    deleted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    restored_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        abstract = True

    def delete(self, deleted_by=None, *args, **kwargs):
        """Override the default delete method to perform a soft delete."""
        self.is_active = False
        self.deleted_at = timezone.now()
        if deleted_by:
            self.deleted_by = deleted_by
        self.save(update_fields=['is_active', 'deleted_at', 'deleted_by'])

    def restore(self, restored_by=None):
        """Custom method to restore a soft-deleted record."""
        self.is_active = True
        self.deleted_at = None
        self.restored_at = timezone.now()
        if restored_by:
            self.restored_by = restored_by
        self.save(update_fields=['is_active', 'deleted_at', 'restored_at', 'restored_by'])

    def hard_delete(self, *args, **kwargs):
        """Use this ONLY if you legally must wipe a record from the database entirely."""
        super().delete(*args, **kwargs)

class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    ROLE_CHOICES = (
        ('ADMIN', 'State Admin'),
        ('FACILITY_IT_ADMIN', 'Facility IT Admin'),
        ('DOCTOR', 'Doctor'),
        ('NURSE', 'Nurse'),
        ('PATIENT', 'Patient'),
    )
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='PATIENT')
    middle_name = models.CharField(max_length=150, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    staff_id = models.CharField(max_length=50, unique=True, null=True, blank=True, editable=False)
    sequence_number = models.BigIntegerField(null=True, blank=True, editable=False, db_index=True)
    facility = models.ForeignKey('facilities.Facility', on_delete=models.SET_NULL, null=True, blank=True, related_name='staff_members')
    suspended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    restored_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    updated_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    deleted_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    def save(self, *args, **kwargs):
        if not self.staff_id and self.role != 'PATIENT':
            with transaction.atomic():
                last_staff = User.objects.exclude(role='PATIENT').exclude(sequence_number__isnull=True).select_for_update().order_by('-sequence_number').first()
                self.sequence_number = (last_staff.sequence_number + 1) if last_staff else 1
                state_code = connection.schema_name.upper()[:3] if connection.schema_name else 'UNK'
                role_prefix = self.role[:3].upper() if self.role else 'STF'
                self.staff_id = f"{role_prefix}-{state_code}-{self.sequence_number:06d}"

        super().save(*args, **kwargs)

    def delete(self, deleted_by=None, *args, **kwargs):
        """Override the default delete method to perform a soft delete."""
        self.is_active = False
        self.deleted_at = timezone.now()
        if deleted_by:
            self.deleted_by = deleted_by
        self.save(update_fields=['is_active', 'deleted_at', 'deleted_by'])

    def restore(self, restored_by=None):
        """Custom method to restore a soft-deleted record."""
        self.is_active = True
        self.deleted_at = None
        self.restored_at = timezone.now()
        if restored_by:
            self.restored_by = restored_by
        self.save(update_fields=['is_active', 'deleted_at', 'restored_at', 'restored_by'])

    def hard_delete(self, *args, **kwargs):
        """Use this ONLY if you legally must wipe a record from the database entirely."""
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.email} - {self.get_role_display()}"
