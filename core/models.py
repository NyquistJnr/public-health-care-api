# core/models.py
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models, transaction, connection
from django.conf import settings
from django.utils import timezone
from core.audit_context import current_request, get_client_ip

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_state = self._get_current_state()

    def _get_current_state(self):
        """Returns a dictionary of the current model fields."""
        return {field.name: getattr(self, field.name) for field in self._meta.fields}

    def _get_changed_fields(self):
        """Compares original state to current state and returns a diff."""
        if not self.pk:
            return {"_all_": "New Object Created"}
            
        changes = {}
        current_state = self._get_current_state()
        for field, old_value in self._original_state.items():
            new_value = current_state[field]
            if old_value != new_value:
                changes[field] = {
                    "old": str(old_value) if old_value is not None else None,
                    "new": str(new_value) if new_value is not None else None
                }
        return changes

    def _log_audit(self, action, changes):
        request = current_request.get()
        
        actor = None
        actor_name = "System Process"
        ip_address = None
        endpoint = None

        if request:
            ip_address = get_client_ip(request)
            endpoint = request.path
            if hasattr(request, 'user') and request.user.is_authenticated:
                actor = request.user
                actor_name = f"{actor.first_name} {actor.last_name} ({actor.staff_id or actor.email})"
            else:
                actor_name = f"Unknown ({ip_address})"

        log_facility = None
        if hasattr(self, 'facility') and self.facility:
            log_facility = self.facility
        elif self.__class__.__name__ == 'Facility':
            log_facility = self
        elif actor and hasattr(actor, 'facility'):
            log_facility = actor.facility

        module = f"{self._meta.app_label.capitalize()} - {self.__class__.__name__}"

        AuditLog.objects.create(
            actor=actor,
            actor_name=actor_name,
            facility=log_facility,
            action=action,
            module=module,
            ip_address=ip_address,
            endpoint=endpoint,
            target_object_id=str(self.pk),
            changes=changes
        )

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        action = "CREATE" if is_new else "UPDATE"
        changes = self._get_changed_fields()
        super().save(*args, **kwargs)
        
        if changes:
            self._log_audit(action, changes)
            self._original_state = self._get_current_state()

    def delete(self, deleted_by=None, *args, **kwargs):
        """Update your soft-delete method to log the deletion."""
        self.is_active = False
        self.deleted_at = timezone.now()
        if deleted_by:
            self.deleted_by = deleted_by
            
        self._log_audit("SUSPEND", {"is_active": {"old": "True", "new": "False"}})
        
        super().save(update_fields=['is_active', 'deleted_at', 'deleted_by'])

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
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True, default='Nigeria')
    profile_picture = models.URLField(max_length=1000, blank=True, null=True, help_text="URL to the hosted image")
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

class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    actor_name = models.CharField(max_length=255, help_text="Stores name or 'Unknown (IP)'")
    action = models.CharField(max_length=50)
    module = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    endpoint = models.CharField(max_length=255, null=True, blank=True)
    target_object_id = models.CharField(max_length=255, null=True, blank=True)
    changes = models.JSONField(null=True, blank=True, help_text="Stores {field: {old: X, new: Y}}")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    facility = models.ForeignKey('facilities.Facility', on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        
    def __str__(self):
        return f"{self.actor_name} -> {self.action} on {self.module} at {self.timestamp}"


class NotificationReadStatus(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audit_log = models.ForeignKey('AuditLog', on_delete=models.CASCADE, related_name='read_statuses')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('audit_log', 'user')
        
    def __str__(self):
        return f"Read by {self.user} - {self.audit_log}"

class PatientProfile(BaseModel):
    SEX_CHOICES = (
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other')
    )
    INSURANCE_STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
        ('NONE', 'None')
    )

    BLOOD_GROUP_CHOICES = (
        ('A+', 'A Positive'), ('A-', 'A Negative'),
        ('B+', 'B Positive'), ('B-', 'B Negative'),
        ('AB+', 'AB Positive'), ('AB-', 'AB Negative'),
        ('O+', 'O Positive'), ('O-', 'O Negative'),
        ('UNKNOWN', 'Unknown')
    )
    
    GENOTYPE_CHOICES = (
        ('AA', 'AA'), ('AS', 'AS'), ('SS', 'SS'), 
        ('AC', 'AC'), ('SC', 'SC'), ('CC', 'CC'), 
        ('UNKNOWN', 'Unknown')
    )

    # Core Links
    user = models.OneToOneField('User', on_delete=models.CASCADE, related_name='patient_profile')
    patient_id = models.CharField(max_length=50, unique=True, editable=False)
    sequence_number = models.BigIntegerField(null=True, blank=True, editable=False, db_index=True)

    # NEW: Biological Constants
    blood_group = models.CharField(max_length=10, choices=BLOOD_GROUP_CHOICES, default='UNKNOWN')
    genotype = models.CharField(max_length=10, choices=GENOTYPE_CHOICES, default='UNKNOWN')

    # Demographics
    sex = models.CharField(max_length=1, choices=SEX_CHOICES)
    date_of_birth = models.DateField(help_text="Always use DOB, age is calculated dynamically.")
    lga = models.CharField(max_length=100, blank=True, null=True)
    ward = models.CharField(max_length=100, blank=True, null=True)

    # Emergency Contacts
    next_of_kin_name = models.CharField(max_length=255, blank=True, null=True)
    next_of_kin_phone = models.CharField(max_length=20, blank=True, null=True)

    # Insurance Information
    insurance_status = models.CharField(max_length=20, choices=INSURANCE_STATUS_CHOICES, default='NONE')
    insurance_provider = models.CharField(max_length=255, blank=True, null=True)
    insurance_package = models.CharField(max_length=255, blank=True, null=True)
    coverage_status = models.CharField(max_length=100, blank=True, null=True)

    # Clinical Summaries
    allergies = models.TextField(blank=True, null=True)
    chronic_conditions = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    mother = models.ForeignKey(
        'core.User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='children_profiles',
        limit_choices_to={'role': 'PATIENT'}
    )
    birth_episode = models.ForeignKey(
        'maternal_care.MaternalCareEpisode', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='newborns'
    )

    def save(self, *args, **kwargs):
        if not self.patient_id:
            with transaction.atomic():
                last_patient = PatientProfile.objects.select_for_update().order_by('-sequence_number').first()
                self.sequence_number = (last_patient.sequence_number + 1) if last_patient else 1
                state_code = connection.schema_name.upper()[:3] if connection.schema_name else 'UNK'
                self.patient_id = f"PT-{state_code}-{self.sequence_number:06d}"
        super().save(*args, **kwargs)

    @property
    def age(self):
        """Calculates exact age based on current date and DOB."""
        if self.date_of_birth:
            today = timezone.now().date()
            return today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
        return None

    @property
    def age_group(self):
        """Dynamically classifies patient into standard clinical age brackets."""
        if not self.date_of_birth:
            return "Unknown"
            
        today = timezone.now().date()
        delta_days = (today - self.date_of_birth).days
        age_years = self.age

        if delta_days <= 28:
            return "Neonate"
        elif age_years < 1:
            return "Infant"
        elif 1 <= age_years <= 3:
            return "Toddler"
        elif 4 <= age_years <= 12:
            return "Child"
        elif 13 <= age_years <= 17:
            return "Adolescent"
        elif 18 <= age_years <= 64:
            return "Adult"
        else:
            return "Senior"

    def __str__(self):
        return f"{self.patient_id} - {self.user.first_name} {self.user.last_name}"
