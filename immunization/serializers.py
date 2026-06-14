from rest_framework import serializers
from .models import ImmunizationRecord
from core.models import PatientProfile
from inventory.models import InventoryItem
from drf_spectacular.utils import extend_schema_field

class NewPatientFastTrackSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    date_of_birth = serializers.DateField()
    sex = serializers.ChoiceField(choices=PatientProfile.SEX_CHOICES)
    next_of_kin_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    next_of_kin_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    next_of_kin_relationship = serializers.CharField(max_length=100, required=False, allow_blank=True) # NEW

class FastTrackImmunizationSerializer(serializers.Serializer):
    session_type = serializers.ChoiceField(choices=ImmunizationRecord.SESSION_TYPES)
    site_name = serializers.CharField(required=False, allow_blank=True)
    state = serializers.CharField(max_length=100)
    lga = serializers.CharField(max_length=100)
    ward = serializers.CharField(max_length=100)
    
    vaccines_given_ids = serializers.ListField(
        child=serializers.PrimaryKeyRelatedField(
            queryset=InventoryItem.objects.filter(drug_classification='IMMUNIZATION')
        ),
        min_length=1,
        help_text="Array of InventoryItem UUIDs"
    )
    
    date_of_visit = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True)
    patient_id = serializers.CharField(required=False, allow_blank=True)
    new_patient_data = NewPatientFastTrackSerializer(required=False)

    def validate_vaccines_given_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Duplicate vaccines detected in the array.")
        return value

    def validate(self, attrs):
        pat_id = attrs.get('patient_id')
        new_data = attrs.get('new_patient_data')

        if not pat_id and not new_data:
            raise serializers.ValidationError("You must provide either an existing 'patient_id' or 'new_patient_data'.")
        if pat_id and new_data:
            raise serializers.ValidationError("Provide either 'patient_id' OR 'new_patient_data', not both.")
        
        if attrs.get('session_type') in ['OUTREACH', 'MOBILE'] and not attrs.get('site_name'):
            raise serializers.ValidationError({"site_name": "Site name is required for Outreach and Mobile sessions."})

        return attrs

class ImmunizationReadSerializer(serializers.ModelSerializer):
    """Used for listing and retrieving immunization records"""
    patient_name = serializers.SerializerMethodField()
    patient_display_id = serializers.CharField(source='patient.patient_profile.patient_id', read_only=True)
    vaccine_name = serializers.CharField(source='vaccine_given.name', read_only=True)
    administered_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ImmunizationRecord
        fields = [
            'id', 'patient', 'patient_name', 'patient_display_id', 
            'appointment', 'facility', 'session_type', 'state', 'lga', 'ward', 'site_name',
            'vaccine_given', 'vaccine_name', 'date_of_visit', 'status', 'age_at_vaccination',
            'notes', 'administered_by', 'administered_by_name', 'created_at', 'updated_at'
        ]

    @extend_schema_field(serializers.CharField())
    def get_patient_name(self, obj):
        return f"{obj.patient.first_name} {obj.patient.last_name}"

    @extend_schema_field(serializers.CharField())
    def get_administered_by_name(self, obj):
        if obj.administered_by:
            return f"{obj.administered_by.first_name} {obj.administered_by.last_name}"
        return "Unknown"


class ImmunizationUpdateSerializer(serializers.ModelSerializer):
    """Restricts updates to safe fields to prevent inventory desyncs."""
    class Meta:
        model = ImmunizationRecord
        fields = ['status', 'session_type', 'site_name', 'state', 'lga', 'ward', 'notes']
