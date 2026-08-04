# core/serializers_reports.py
"""Response serializers for core/view_reports.py - used purely so drf-spectacular can
document these views; the views build their response dicts by hand."""
from rest_framework import serializers


class DailyActivityRowSerializer(serializers.Serializer):
    """Also used as DailyActivityReportView.serializer_class (drives the paginated list)."""
    date = serializers.DateField()
    patient_visits = serializers.IntegerField()
    diagnosis = serializers.IntegerField()
    lab_tests = serializers.IntegerField()
    prescriptions = serializers.IntegerField()
    appointments = serializers.IntegerField()


class ReportPeriodSerializer(serializers.Serializer):
    start_date = serializers.CharField(allow_null=True)
    end_date = serializers.CharField(allow_null=True, help_text="A date, or 'All Time' when no date filters were provided")


class ModuleReportItemSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    completed = serializers.IntegerField()
    summary = serializers.CharField()


class ComprehensiveModuleReportResponseSerializer(serializers.Serializer):
    period = ReportPeriodSerializer()
    reports = serializers.DictField(
        child=ModuleReportItemSerializer(),
        help_text="Keyed by module name, e.g. 'patients', 'appointments', 'ancs'"
    )


class ModuleCompletionItemSerializer(serializers.Serializer):
    module_name = serializers.CharField()
    total_count = serializers.IntegerField()
    completed_count = serializers.IntegerField()
    completion_percentage = serializers.FloatField()


class ModuleCompletionPercentageResponseSerializer(serializers.Serializer):
    period = ReportPeriodSerializer()
    modules = ModuleCompletionItemSerializer(many=True)
