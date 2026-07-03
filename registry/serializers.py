# registry/serializers.py
from rest_framework import serializers

from .models import Disease, SystemThreshold


class DiseaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Disease
        fields = ['id', 'name', 'severity', 'description', 'is_active', 'created_at', 'updated_at']
        read_only_fields = fields


class DiseaseSummarySerializer(serializers.ModelSerializer):
    """Compact nested representation, used when a Disease is embedded in another resource (e.g. Consultation)."""

    class Meta:
        model = Disease
        fields = ['id', 'name', 'severity']
        read_only_fields = fields


class SystemThresholdSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemThreshold
        fields = [
            'disease_compliance_threshold_percent', 'failed_login_attempts_threshold',
            'system_error_threshold', 'inactive_facility_threshold_days',
            'high_usage_threshold_users', 'updated_at'
        ]
        read_only_fields = ['updated_at']
