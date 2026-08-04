# core/serializers_clinical_stats.py
"""Response serializers for core/view_clinical_stats.py - used purely so drf-spectacular can
document these views; the views build their response dicts by hand."""
from rest_framework import serializers


class ReferredPatientsSerializer(serializers.Serializer):
    out = serializers.IntegerField()
    total = serializers.IntegerField()

    def __init__(self, *args, **kwargs):
        # 'in' is a Python keyword, so it can't be declared as a class attribute above -
        # add it to the field set directly instead.
        super().__init__(*args, **kwargs)
        self.fields['in'] = serializers.IntegerField()


class TodaysPatientsSerializer(serializers.Serializer):
    waiting_patients = serializers.IntegerField()
    seen_attended_to_patient = serializers.IntegerField()
    referred_patients = ReferredPatientsSerializer()


class ClinicalStatsResponseSerializer(serializers.Serializer):
    todays_patients = TodaysPatientsSerializer()
    consultations = serializers.IntegerField()
    lab_tests = serializers.IntegerField()


class PatientVisitTrendPointSerializer(serializers.Serializer):
    date = serializers.DateField()
    count = serializers.IntegerField()


class PatientVisitTrendResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    trend = PatientVisitTrendPointSerializer(many=True)


class ClinicalActivityResponseSerializer(serializers.Serializer):
    consultations = serializers.IntegerField()
    lab_tests = serializers.IntegerField()
    prescriptions = serializers.IntegerField()


class DiseaseOverviewItemSerializer(serializers.Serializer):
    disease = serializers.CharField()
    count = serializers.IntegerField()
    percentage = serializers.FloatField()


class DiseaseOverviewResponseSerializer(serializers.Serializer):
    total_diagnoses = serializers.IntegerField()
    diseases = DiseaseOverviewItemSerializer(many=True)
