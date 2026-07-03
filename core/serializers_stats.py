# core/serializers_stats.py
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .utils import facility_status_from_last_active, format_last_active_label


class ActiveFacilitiesSerializer(serializers.Serializer):
    active = serializers.IntegerField()
    total = serializers.IntegerField()


class DashboardStatsSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    total_active_users = serializers.IntegerField()
    active_facilities = ActiveFacilitiesSerializer()
    total_logins = serializers.IntegerField()
    active_sessions = serializers.CharField(help_text="Formatted as 'Xh Ym'")
    active_sessions_minutes = serializers.IntegerField()


class UserActivityTrendDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    active_users = serializers.IntegerField(help_text="Distinct users who logged in on this day")
    logins = serializers.IntegerField(help_text="Total logins on this day")


class UserActivityTrendSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    results = UserActivityTrendDaySerializer(many=True)


class ModuleUsageItemSerializer(serializers.Serializer):
    module = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()
    percentage = serializers.FloatField()


class ModuleUsageStatsSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    results = ModuleUsageItemSerializer(many=True)


class TopActiveFacilitySerializer(serializers.Serializer):
    facility_id = serializers.UUIDField(source='id')
    facility_name = serializers.CharField(source='name')
    usage_count = serializers.IntegerField()
    percentage = serializers.SerializerMethodField()

    @extend_schema_field(serializers.FloatField())
    def get_percentage(self, obj):
        total = self.context.get('total_usage') or 0
        if not total:
            return 0.0
        return round((obj.usage_count / total) * 100, 2)


class FacilityUsageTableSerializer(serializers.Serializer):
    facility_id = serializers.UUIDField(source='id')
    facility_name = serializers.CharField(source='name')
    number_of_users = serializers.IntegerField()
    number_of_logins = serializers.IntegerField()
    last_active = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    @extend_schema_field(serializers.CharField())
    def get_last_active(self, obj):
        return format_last_active_label(obj.last_active_at)

    @extend_schema_field(serializers.CharField())
    def get_status(self, obj):
        return facility_status_from_last_active(obj.last_active_at)
