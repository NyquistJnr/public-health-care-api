# consultations/serializers.py
from rest_framework import serializers
from django.db import transaction
from .models import Consultation
from drf_spectacular.utils import extend_schema_field, inline_serializer
from registry.serializers import DiseaseSummarySerializer

class ConsultationReadSerializer(serializers.ModelSerializer):
    patient_display_id = serializers.CharField(source='patient.patient_profile.patient_id', read_only=True)
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    patient_age = serializers.CharField(source='patient.patient_profile.age_group', read_only=True)
    patient_gender = serializers.CharField(source='patient.patient_profile.get_sex_display', read_only=True)
    doctor_name = serializers.CharField(source='doctor.get_full_name', read_only=True)
    diagnosed_disease = DiseaseSummarySerializer(read_only=True)

    vitals = serializers.SerializerMethodField()

    class Meta:
        model = Consultation
        fields = [
            'id', 'consultation_id', 'appointment', 'patient', 'patient_display_id',
            'patient_name', 'patient_age', 'patient_gender', 'doctor', 'doctor_name',
            'chief_complaint', 'history_of_present_complaint',
            'past_medical_history', 'examination_findings', 'primary_diagnosis',
            'secondary_diagnosis', 'diagnosed_disease', 'treatment_plan', 'additional_notes',
            'vitals', 'created_at'
        ]

    @extend_schema_field(
        inline_serializer(
            name='ConsultationVitals',
            fields={
                'blood_pressure': serializers.CharField(allow_null=True, required=False),
                'temperature': serializers.DecimalField(max_digits=4, decimal_places=1, allow_null=True, required=False),
                'pulse_rate': serializers.IntegerField(allow_null=True, required=False),
                'respiratory_rate': serializers.IntegerField(allow_null=True, required=False),
                'weight_kg': serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True, required=False),
                'spo2': serializers.IntegerField(allow_null=True, required=False),
                'bmi': serializers.FloatField(allow_null=True, required=False),
            }
        )
    )
    def get_vitals(self, obj):
        vital_record = obj.appointment.vitals.first()
        if vital_record:
            return {
                "blood_pressure": vital_record.blood_pressure,
                "temperature": vital_record.temperature,
                "pulse_rate": vital_record.pulse_rate,
                "respiratory_rate": vital_record.respiratory_rate,
                "weight_kg": vital_record.weight_kg,
                "spo2": vital_record.spo2,
                "bmi": vital_record.bmi,
            }
        return None


class ConsultationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Consultation
        fields = [
            'appointment', 'chief_complaint',
            'history_of_present_complaint', 'past_medical_history',
            'examination_findings', 'primary_diagnosis', 'secondary_diagnosis',
            'diagnosed_disease', 'treatment_plan', 'additional_notes'
        ]

    @transaction.atomic
    def create(self, validated_data):
        appointment = validated_data['appointment']
        user = self.context['request'].user
        validated_data['patient'] = appointment.patient
        validated_data['doctor'] = user
        validated_data['created_by'] = user
        consultation = super().create(validated_data)
        appointment.status = 'COMPLETED'
        appointment.save(update_fields=['status', 'updated_at'])

        return consultation
