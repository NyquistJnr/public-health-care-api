# doctors/serializers.py
from rest_framework import serializers

class DoctorStatsResponseSerializer(serializers.Serializer):
    waiting = serializers.IntegerField()
    in_consultation = serializers.IntegerField()
    completed = serializers.IntegerField()
    pending_labs = serializers.IntegerField()

class UnifiedAlertItemSerializer(serializers.Serializer):
    alert_type = serializers.CharField(help_text="ANC, PNC, IMMUNIZATION, REFERRAL, LAB")
    patient_name = serializers.CharField()
    patient_id = serializers.CharField(required=False, allow_null=True)
    date = serializers.DateTimeField(help_text="The target date or last updated timestamp")
    status = serializers.CharField()
    details = serializers.CharField(help_text="Contextual info like 'Test Name' or 'Facility Name'")

class PaginatedDoctorAlertsResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    current_page = serializers.IntegerField()
    next = serializers.URLField(allow_null=True, required=False)
    previous = serializers.URLField(allow_null=True, required=False)
    results = UnifiedAlertItemSerializer(many=True, help_text="Sorted by closest to current date/time")
