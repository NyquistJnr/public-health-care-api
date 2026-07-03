# core/serializers_alerts.py
from rest_framework import serializers


class AlertItemSerializer(serializers.Serializer):
    type = serializers.CharField()
    severity = serializers.CharField()
    title = serializers.CharField()
    message = serializers.CharField()
    facility_id = serializers.CharField(allow_null=True)
    facility_name = serializers.CharField(allow_null=True)
    disease = serializers.CharField(allow_null=True)
    detected_at = serializers.DateTimeField()
    metric_value = serializers.FloatField()
    threshold_value = serializers.FloatField(allow_null=True)
