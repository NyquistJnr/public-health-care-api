# maternal_care/serializers.py
from rest_framework import serializers
from .models import (
    MaternalCareEpisode, ANCVisit, PNCVisit, 
    PNCNewbornAssessment, MaternalScheduleRule
)
from core.models import PatientProfile

class MaternalScheduleRuleSerializer(serializers.ModelSerializer):
    """Serializer for configuring Global State-Level ANC/PNC Scheduling Rules."""
    class Meta:
        model = MaternalScheduleRule
        fields = [
            'id', 'care_type', 'rule_type', 'interval_days', 
            'intervals_sequence', 'visit_tasks', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        rule_type = attrs.get('rule_type')
        if rule_type == 'RECURRING' and not attrs.get('interval_days'):
            raise serializers.ValidationError({"interval_days": "Must provide interval_days for RECURRING rules."})
        if rule_type == 'VARIABLE_SEQUENCE' and not attrs.get('intervals_sequence'):
            raise serializers.ValidationError({"intervals_sequence": "Must provide intervals_sequence array for VARIABLE_SEQUENCE rules."})
        return attrs


class MaternalCareEpisodeSerializer(serializers.ModelSerializer):
    """Main serializer for Pregnancy Episodes, including patient details and custom override schedules."""
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    patient_display_id = serializers.CharField(source='patient.patient_profile.patient_id', read_only=True)
    
    class Meta:
        model = MaternalCareEpisode
        fields = [
            'id', 'episode_id', 'patient', 'patient_name', 'patient_display_id', 'status',
            'last_menstrual_period', 'expected_date_of_delivery', 'gravida', 'parity',
            'living_children', 'partner_name', 'partner_phone', 
            'custom_anc_schedule', 'custom_pnc_schedule', 'created_at'
        ]
        read_only_fields = ['id', 'episode_id', 'expected_date_of_delivery', 'created_at']


class ANCVisitSerializer(serializers.ModelSerializer):
    """Serializer for individual Antenatal Care visits."""
    appointment_date = serializers.DateField(source='appointment.appointment_date', read_only=True)
    
    class Meta:
        model = ANCVisit
        fields = '__all__'
        read_only_fields = [
            'id', 'visit_sequence_number', 'next_visit_date', 
            'recommended_tasks', 'created_at', 'updated_at', 'created_by'
        ]


class PNCNewbornAssessmentSerializer(serializers.ModelSerializer):
    """Serializer for assessing newborns during a PNC visit."""
    baby_name = serializers.CharField(source='baby.get_full_name', read_only=True)
    baby_display_id = serializers.CharField(source='baby.patient_profile.patient_id', read_only=True)

    class Meta:
        model = PNCNewbornAssessment
        fields = [
            'id', 'pnc_visit', 'baby', 'baby_name', 'baby_display_id', 'cord_care_assessed',
            'temperature', 'exclusive_breastfeeding', 'newborn_danger_signs',
            'neonatal_jaundice', 'first_dose_antibiotics_given', 'kmc_provided', 'outcome'
        ]


class PNCVisitSerializer(serializers.ModelSerializer):
    """Serializer for Postnatal Care visits, including nested newborn assessments."""
    appointment_date = serializers.DateField(source='appointment.appointment_date', read_only=True)
    newborn_assessments = PNCNewbornAssessmentSerializer(many=True, read_only=True)
    
    class Meta:
        model = PNCVisit
        fields = [
            'id', 'episode', 'appointment', 'appointment_date', 'attendance_type',
            'visit_sequence_number', 'next_visit_date', 'recommended_tasks',
            'timing_of_visit', 'vaginal_examination_conducted', 'hemoglobin_pcv',
            'urinalysis', 'counselling_topics', 'outcome', 'referral_reason',
            'newborn_assessments', 'created_at'
        ]
        read_only_fields = [
            'id', 'visit_sequence_number', 'next_visit_date', 
            'recommended_tasks', 'created_at', 'updated_at', 'created_by'
        ]

class NewbornRegistrationSerializer(serializers.Serializer):
    """Details for a single newborn (used during delivery recording)."""
    first_name = serializers.CharField(max_length=150, help_text="e.g., Baby 1, or actual name if given")
    last_name = serializers.CharField(max_length=150, help_text="Usually the father's or mother's surname")
    sex = serializers.ChoiceField(choices=PatientProfile.SEX_CHOICES)
    weight_kg = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)


class RecordDeliverySerializer(serializers.Serializer):
    """Payload for recording a delivery and auto-registering the babies."""
    delivery_date = serializers.DateField()
    babies = NewbornRegistrationSerializer(many=True, help_text="List of babies born (handles twins/triplets)")


class EpisodeBabySerializer(serializers.Serializer):
    """Formats the output for babies born during a specific episode."""
    id = serializers.UUIDField()
    patient_display_id = serializers.CharField(source='patient_profile.patient_id', read_only=True)
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    sex = serializers.CharField(source='patient_profile.sex', read_only=True)
    date_of_birth = serializers.DateField(source='patient_profile.date_of_birth', read_only=True)
