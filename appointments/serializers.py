from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
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


class AppointmentWriteSerializer(serializers.ModelSerializer):
    """Used for creating and updating appointments"""
    class Meta:
        model = Appointment
        fields = [
            'patient', 'assigned_to', 'appointment_date', 
            'appointment_time', 'visit_type', 'reason_for_visit', 'notes'
        ]

    def validate(self, attrs):
        assigned_to = attrs.get('assigned_to')
        apt_date = attrs.get('appointment_date')
        apt_time = attrs.get('appointment_time')

        if assigned_to and apt_date and apt_time:
            is_booked = Appointment.objects.filter(
                assigned_to=assigned_to,
                appointment_date=apt_date,
                appointment_time=apt_time,
                status__in=['SCHEDULED', 'IN_PROGRESS']
            ).exists()

            if is_booked:
                raise serializers.ValidationError({
                    "appointment_time": f"Dr/Nurse {assigned_to.last_name} already has an active appointment scheduled at this exact time."
                })

        return attrs

class AppointmentStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Appointment.STATUS_CHOICES)



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
