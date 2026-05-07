from rest_framework import serializers
from .models import ImmunizationRecord
from core.models import PatientProfile
from inventory.models import Drug

class NewPatientFastTrackSerializer(serializers.Serializer):
    """Basic demographic data needed to instantly register a child in the field"""
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    date_of_birth = serializers.DateField()
    sex = serializers.ChoiceField(choices=PatientProfile.SEX_CHOICES)
    next_of_kin_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    next_of_kin_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)

class FastTrackImmunizationSerializer(serializers.Serializer):
    """The Unified Payload for the Mobile/Outreach App"""
    session_type = serializers.ChoiceField(choices=ImmunizationRecord.SESSION_TYPES)
    site_name = serializers.CharField(required=False, allow_blank=True)
    state = serializers.CharField(max_length=100)
    lga = serializers.CharField(max_length=100)
    ward = serializers.CharField(max_length=100)
    
    vaccine_given_id = serializers.PrimaryKeyRelatedField(queryset=Drug.objects.all(), source='vaccine_given')
    date_of_visit = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True)

    patient_id = serializers.CharField(required=False, allow_blank=True, help_text="e.g., PT-LAG-000012")
    new_patient_data = NewPatientFastTrackSerializer(required=False)

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
