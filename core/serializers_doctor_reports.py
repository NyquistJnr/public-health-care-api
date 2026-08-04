# core/serializers_doctor_reports.py
"""Response serializers for core/view_doctor_reports.py - used purely so drf-spectacular can
document these endpoints. The two aggregate reports (Consultation Report, Disease Morbidity
Report, Clinical Outcome Report) build their response dicts by hand and don't call these
serializers at runtime. The two table reports (Referral Report, Adverse Events Report) are
real paginated ModelSerializer-backed list endpoints."""
from datetime import date
from typing import Optional

from rest_framework import serializers

from adverse_events.models import AdverseEvent
from referrals.models import Referral


class DiagnosisDistributionRowSerializer(serializers.Serializer):
    diagnosis = serializers.CharField(help_text="Verbatim primary_diagnosis text as entered by the doctor")
    count = serializers.IntegerField()


class TreatmentProvidedRowSerializer(serializers.Serializer):
    treatment = serializers.CharField(help_text="Drug/treatment name from the doctor's prescriptions")
    count = serializers.IntegerField()


class ReferralStatusRowSerializer(serializers.Serializer):
    status = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()


class ConsultationOutcomeRowSerializer(serializers.Serializer):
    outcome = serializers.CharField(help_text="Derived from appointment status + whether a referral was made - Consultation has no dedicated outcome field")
    count = serializers.IntegerField()


class ConsultationReportResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    total_consultations = serializers.IntegerField()
    diagnosis_distribution = DiagnosisDistributionRowSerializer(many=True)
    treatment_provided = TreatmentProvidedRowSerializer(many=True)
    referral_status = ReferralStatusRowSerializer(many=True)
    consultation_outcome = ConsultationOutcomeRowSerializer(many=True)


class DiseaseMorbidityRowSerializer(serializers.Serializer):
    disease = serializers.CharField()
    male = serializers.IntegerField()
    female = serializers.IntegerField()
    under_5 = serializers.IntegerField()
    above_5 = serializers.IntegerField()
    total = serializers.IntegerField()


class DiseaseMorbidityReportResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    results = DiseaseMorbidityRowSerializer(many=True)


class DoctorReferralRowSerializer(serializers.ModelSerializer):
    patient = serializers.SerializerMethodField()
    referral_date = serializers.SerializerMethodField()
    reason = serializers.CharField(source='reason_for_referral')
    receiving_facility = serializers.SerializerMethodField()
    status_label = serializers.CharField(source='get_status_display')
    urgency = serializers.SerializerMethodField()

    class Meta:
        model = Referral
        fields = ['referral_id', 'patient', 'referral_date', 'reason', 'receiving_facility', 'status', 'status_label', 'urgency']

    def get_patient(self, obj) -> str:
        return f"{obj.patient.first_name} {obj.patient.last_name}"

    def get_referral_date(self, obj) -> date:
        return obj.created_at.date()

    def get_receiving_facility(self, obj) -> str:
        return obj.receiving_facility.name if obj.receiving_facility else obj.get_destination_level_display()

    def get_urgency(self, obj) -> str:
        return "Emergency" if obj.referral_type == 'EMERGENCY' else "Routine"


class DoctorAdverseEventRowSerializer(serializers.ModelSerializer):
    patient = serializers.SerializerMethodField()
    encounter_date = serializers.DateField(source='date_of_reaction')
    medicine_treatment = serializers.CharField(source='suspected_drug.name')
    adverse_event = serializers.CharField(source='reaction_type')
    action_taken = serializers.SerializerMethodField()
    reported_by = serializers.SerializerMethodField()

    class Meta:
        model = AdverseEvent
        fields = ['event_id', 'patient', 'encounter_date', 'medicine_treatment', 'adverse_event', 'severity', 'action_taken', 'reported_by', 'status']

    def get_patient(self, obj) -> str:
        return f"{obj.patient.first_name} {obj.patient.last_name}"

    def get_action_taken(self, obj) -> Optional[str]:
        return obj.closed_comment or obj.resolved_comment or obj.under_review_comment or obj.reported_comment or None

    def get_reported_by(self, obj) -> Optional[str]:
        return f"{obj.reported_by.first_name} {obj.reported_by.last_name}" if obj.reported_by else None


class ClinicalOutcomeReportResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    recovered = serializers.IntegerField(help_text="PLACEHOLDER - no general clinical recovery/discharge model exists yet")
    admitted = serializers.IntegerField(help_text="PLACEHOLDER - PatientProfile.birth_status=ADMITTED only tracks newborns, not general admissions")
    transferred = serializers.IntegerField(help_text="PLACEHOLDER - no facility-transfer tracking model exists yet")
    referred = serializers.IntegerField(help_text="Real count - referrals this doctor initiated in the period")
    deaths = serializers.IntegerField(help_text="PLACEHOLDER - no general mortality register exists yet (birth_status=DEAD only tracks neonatal deaths)")
