from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import Appointment
from core.models import User

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
            'visit_type', 'status', 'reason_for_visit', 'notes', 
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
