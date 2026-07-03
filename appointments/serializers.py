# appointments/serializers.py

import uuid
from django.db import transaction
from django.contrib.auth.models import Group
from django.core.validators import RegexValidator
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import User, PatientProfile
from .models import Appointment, Vitals


class AppointmentReadSerializer(serializers.ModelSerializer):
    """Used for returning data to the frontend (List & Retrieve)"""
    patient_name = serializers.SerializerMethodField()
    patient_display_id = serializers.CharField(source='patient.patient_profile.patient_id', read_only=True)
    assigned_staff_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = [
            'id', 'appointment_id', 'patient', 'patient_name', 'patient_display_id',
            'assigned_to', 'assigned_staff_name', 'appointment_date', 'appointment_time',
            'visit_type', 'status', 'priority', 'reason_for_visit', 'notes',
            'created_by', 'created_by_name', 'created_at'
        ]

    @extend_schema_field(serializers.CharField())
    def get_patient_name(self, obj):
        return f"{obj.patient.first_name} {obj.patient.last_name}"

    @extend_schema_field(serializers.CharField())
    def get_assigned_staff_name(self, obj):
        if obj.assigned_to:
            return f"{obj.assigned_to.first_name} {obj.assigned_to.last_name} ({obj.assigned_to.get_role_display()})"
        return "Unassigned"

    @extend_schema_field(serializers.CharField())
    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}"
        return "System"


_bp_validator = RegexValidator(
    regex=r'^\d{2,3}/\d{2,3}$',
    message="BP must be in format Systolic/Diastolic (e.g., 120/80)"
)


class BlankableIntegerField(serializers.IntegerField):
    """IntegerField that treats an empty string as null, like DRF's DecimalField already does."""
    def validate_empty_values(self, data):
        if isinstance(data, str) and data.strip() == '' and self.allow_null:
            return (True, None)
        return super().validate_empty_values(data)


class AppointmentWriteSerializer(serializers.ModelSerializer):
    """Used for creating and updating appointments.

    On create, you may either supply an existing `patient` UUID or inline
    patient fields (first_name, last_name, sex, date_of_birth are required
    for inline registration).  Vitals can also be recorded at the same time.
    """

    patient = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role='PATIENT'),
        required=False,
    )

    # ── Inline patient registration (write-only) ──────────────────────────
    first_name = serializers.CharField(required=False, write_only=True)
    last_name = serializers.CharField(required=False, write_only=True)
    middle_name = serializers.CharField(required=False, allow_blank=True, write_only=True)
    phone_number = serializers.CharField(required=False, allow_blank=True, write_only=True)
    email = serializers.EmailField(required=False, allow_blank=True, write_only=True)
    sex = serializers.ChoiceField(choices=PatientProfile.SEX_CHOICES, required=False, write_only=True)
    date_of_birth = serializers.DateField(required=False, write_only=True)
    lga = serializers.CharField(required=False, allow_blank=True, write_only=True)
    ward = serializers.CharField(required=False, allow_blank=True, write_only=True)
    blood_group = serializers.ChoiceField(choices=PatientProfile.BLOOD_GROUP_CHOICES, required=False, write_only=True)
    genotype = serializers.ChoiceField(choices=PatientProfile.GENOTYPE_CHOICES, required=False, write_only=True)
    next_of_kin_name = serializers.CharField(required=False, allow_blank=True, write_only=True)
    next_of_kin_phone = serializers.CharField(required=False, allow_blank=True, write_only=True)

    # ── Inline vitals recording (write-only, all optional) ────────────────
    temperature = serializers.DecimalField(max_digits=4, decimal_places=1, required=False, write_only=True, allow_null=True)
    blood_pressure = serializers.CharField(
        max_length=7, required=False, write_only=True,
        allow_null=True, allow_blank=True,
        validators=[_bp_validator],
    )
    pulse_rate = BlankableIntegerField(required=False, write_only=True, allow_null=True)
    respiratory_rate = BlankableIntegerField(required=False, write_only=True, allow_null=True)
    weight_kg = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, write_only=True, allow_null=True)
    height_cm = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, write_only=True, allow_null=True)
    spo2 = BlankableIntegerField(required=False, write_only=True, allow_null=True)
    vitals_notes = serializers.CharField(required=False, write_only=True, allow_null=True, allow_blank=True)

    class Meta:
        model = Appointment
        fields = [
            'patient', 'assigned_to', 'appointment_date',
            'appointment_time', 'visit_type', 'reason_for_visit', 'notes',
            # Inline patient
            'first_name', 'last_name', 'middle_name', 'phone_number', 'email',
            'sex', 'date_of_birth', 'lga', 'ward', 'blood_group', 'genotype',
            'next_of_kin_name', 'next_of_kin_phone',
            # Inline vitals
            'temperature', 'blood_pressure', 'pulse_rate', 'respiratory_rate',
            'weight_kg', 'height_cm', 'spo2', 'vitals_notes',
        ]

    def validate(self, attrs):
        # Patient validation only on create
        if not self.instance:
            patient = attrs.get('patient')
            if not patient:
                if not (attrs.get('first_name') and attrs.get('last_name')
                        and attrs.get('sex') and attrs.get('date_of_birth')):
                    raise serializers.ValidationError({
                        "patient": (
                            "Provide an existing patient ID, or supply first_name, "
                            "last_name, sex, and date_of_birth to register a new patient inline."
                        )
                    })

        assigned_to = attrs.get('assigned_to')
        apt_date = attrs.get('appointment_date')
        apt_time = attrs.get('appointment_time')

        if assigned_to and apt_date and apt_time:
            qs = Appointment.objects.filter(
                assigned_to=assigned_to,
                appointment_date=apt_date,
                appointment_time=apt_time,
                status__in=['SCHEDULED', 'IN_PROGRESS']
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    "appointment_time": (
                        f"Dr/Nurse {assigned_to.last_name} already has an active "
                        "appointment scheduled at this exact time."
                    )
                })

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        _patient_user_fields = [
            'first_name', 'last_name', 'middle_name', 'phone_number', 'email',
        ]
        _patient_profile_fields = [
            'sex', 'date_of_birth', 'lga', 'ward', 'blood_group', 'genotype',
            'next_of_kin_name', 'next_of_kin_phone',
        ]
        _vitals_fields = [
            'temperature', 'blood_pressure', 'pulse_rate', 'respiratory_rate',
            'weight_kg', 'height_cm', 'spo2', 'vitals_notes',
        ]

        # Pull out inline patient data
        patient_data = {
            f: validated_data.pop(f)
            for f in _patient_user_fields + _patient_profile_fields
            if f in validated_data
        }

        # Pull out inline vitals data (skip null / blank values)
        vitals_data = {}
        for field in _vitals_fields:
            if field in validated_data:
                value = validated_data.pop(field)
                if value is not None and value != '':
                    vitals_data['notes' if field == 'vitals_notes' else field] = value

        # Create patient inline if no existing patient supplied
        if not validated_data.get('patient') and patient_data:
            facility = validated_data.get('facility')
            request = self.context.get('request')
            creator = request.user if request else None

            email = patient_data.get('email', '')
            patient_user = User(
                first_name=patient_data.get('first_name', ''),
                last_name=patient_data.get('last_name', ''),
                middle_name=patient_data.get('middle_name'),
                phone_number=patient_data.get('phone_number'),
                email=email,
                username=email if email else f"patient_{uuid.uuid4().hex[:10]}",
                role='PATIENT',
                facility=facility,
                created_by=creator,
            )
            patient_user.set_unusable_password()
            patient_user.save()

            try:
                group = Group.objects.get(name='PATIENT')
                patient_user.groups.add(group)
            except Group.DoesNotExist:
                pass

            profile_fields = {
                k: v for k, v in patient_data.items()
                if k in _patient_profile_fields
            }
            PatientProfile.objects.create(user=patient_user, created_by=creator, **profile_fields)
            validated_data['patient'] = patient_user

        creator = validated_data.get('created_by')
        appointment = Appointment.objects.create(**validated_data)

        # Always create a vitals record so the pending-vitals queue is populated.
        # If vitals data was supplied, it records measurements immediately and
        # transitions the appointment to VITALS_DONE via Vitals.save().
        Vitals.objects.create(
            appointment=appointment,
            patient=appointment.patient,
            created_by=creator,
            **vitals_data,
        )

        return appointment

    def update(self, instance, validated_data):
        # Inline-creation fields have no meaning on updates — strip them
        for field in [
            'first_name', 'last_name', 'middle_name', 'phone_number', 'email',
            'sex', 'date_of_birth', 'lga', 'ward', 'blood_group', 'genotype',
            'next_of_kin_name', 'next_of_kin_phone',
            'temperature', 'blood_pressure', 'pulse_rate', 'respiratory_rate',
            'weight_kg', 'height_cm', 'spo2', 'vitals_notes',
        ]:
            validated_data.pop(field, None)
        return super().update(instance, validated_data)


class AppointmentStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Appointment.STATUS_CHOICES)


class AppointmentAssignSerializer(serializers.Serializer):
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role__in=['DOCTOR', 'NURSE']),
        help_text="UUID of the Doctor/Nurse to hand this appointment off to after vitals."
    )


#### Vitals Serializers ####

class VitalsSerializer(serializers.ModelSerializer):
    bmi = serializers.SerializerMethodField()
    age = serializers.SerializerMethodField()
    visit_type = serializers.CharField(source='appointment.visit_type', read_only=True)
    appointment_status = serializers.CharField(source='appointment.status', read_only=True)
    appointment_priority = serializers.CharField(source='appointment.priority', read_only=True)
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    patient_display_id = serializers.CharField(source='patient.patient_profile.patient_id', read_only=True)
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Vitals
        fields = [
            'id', 'vital_id', 'appointment', 'patient_display_id', 'patient_name',
            'visit_type', 'appointment_status', 'appointment_priority', 'age',
            'temperature', 'blood_pressure', 'pulse_rate', 'respiratory_rate',
            'weight_kg', 'height_cm', 'bmi', 'spo2', 'notes',
            'created_by', 'recorded_by_name', 'created_at'
        ]

        read_only_fields = ['id', 'vital_id', 'created_by', 'created_at']

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_bmi(self, obj):
        return obj.bmi

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_age(self, obj):
        return obj.age_at_visit

    @extend_schema_field(serializers.CharField())
    def get_recorded_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name} ({obj.created_by.get_role_display()})"
        return "System"

    def validate(self, attrs):
        appointment = attrs.get('appointment')

        if appointment and appointment.status in ['CANCELLED', 'NO_SHOW']:
            raise serializers.ValidationError({"appointment": "Cannot record vitals for a cancelled or no-show appointment."})

        return attrs
