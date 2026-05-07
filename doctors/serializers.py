# doctors/serializers.py
from rest_framework import serializers
from laboratory.serializers import LabRequestReadSerializer

class DoctorStatsResponseSerializer(serializers.Serializer):
    waiting = serializers.IntegerField()
    in_consultation = serializers.IntegerField()
    completed = serializers.IntegerField()
    pending_labs = serializers.IntegerField()

class PregnancyAlertSerializer(serializers.Serializer):
    high_risk_count = serializers.IntegerField()

class ImmunizationAlertSerializer(serializers.Serializer):
    due_for_immunization = serializers.IntegerField()

class ReferralAlertSerializer(serializers.Serializer):
    total_pending = serializers.IntegerField()
    recent_pending = serializers.ListField(child=serializers.DictField())

class LabAlertSerializer(serializers.Serializer):
    ready_24h_count = serializers.IntegerField()
    pending_count = serializers.IntegerField()
    recent_ready_tests = serializers.ListField(child=serializers.DictField())
    recent_pending_requests = serializers.ListField(child=serializers.DictField())

class DoctorAlertsResponseSerializer(serializers.Serializer):
    pregnancy = PregnancyAlertSerializer(required=False)
    immunization = ImmunizationAlertSerializer(required=False)
    referrals = ReferralAlertSerializer(required=False)
    labs = LabAlertSerializer(required=False)
