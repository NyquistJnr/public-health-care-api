# core/serializers_state_admin_reports.py
"""Response serializers for core/view_state_admin_reports.py - used purely so drf-spectacular
can document these APIViews; the views build their response dicts by hand and don't call
these serializers at runtime."""
from rest_framework import serializers


class FacilityPerformanceRowSerializer(serializers.Serializer):
    facility_id = serializers.UUIDField()
    facility = serializers.CharField()
    facility_code = serializers.CharField()
    lga = serializers.CharField()
    patients_seen = serializers.IntegerField()
    reports_submitted = serializers.IntegerField(help_text="PLACEHOLDER - no report-submission tracking model exists yet")
    reporting_timeliness = serializers.FloatField(help_text="PLACEHOLDER - static 100.0 until real tracking exists")
    referral_rate = serializers.FloatField(help_text="referrals_sent / patients_seen * 100")
    performance_score = serializers.FloatField(help_text="Composite: 60% patient throughput (capped at 100) + 40% reporting timeliness")


class FacilityPerformanceReportResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    results = FacilityPerformanceRowSerializer(many=True)


class MaternalHealthRowSerializer(serializers.Serializer):
    facility_id = serializers.UUIDField()
    facility = serializers.CharField()
    lga = serializers.CharField()
    anc_1 = serializers.IntegerField()
    anc_4 = serializers.IntegerField()
    deliveries = serializers.IntegerField()
    maternal_deaths = serializers.IntegerField(help_text="PLACEHOLDER - no maternal mortality register exists yet")
    neonatal_deaths = serializers.IntegerField()
    iptp_coverage = serializers.FloatField(help_text="Percentage of ANC visits with an IPTp dose recorded")


class MaternalHealthChartRowSerializer(serializers.Serializer):
    facility = serializers.CharField()
    anc_1 = serializers.IntegerField()
    anc_4 = serializers.IntegerField()
    iptp_coverage = serializers.FloatField()


class MaternalHealthReportResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    results = MaternalHealthRowSerializer(many=True)
    state_comparison_chart = MaternalHealthChartRowSerializer(many=True)


class ChildHealthRowSerializer(serializers.Serializer):
    facility_id = serializers.UUIDField()
    facility = serializers.CharField()
    lga = serializers.CharField()
    bcg = serializers.IntegerField()
    penta_1 = serializers.IntegerField()
    penta_3 = serializers.IntegerField()
    measles = serializers.IntegerField()
    sam_cases = serializers.IntegerField(help_text="PLACEHOLDER - no malnutrition/SAM model exists yet")
    growth_monitoring = serializers.IntegerField(help_text="PLACEHOLDER - no growth-monitoring model exists yet")


class ChildHealthReportResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    results = ChildHealthRowSerializer(many=True)


class DiseaseSurveillanceRowSerializer(serializers.Serializer):
    """Also used as DiseaseSurveillanceReportView.serializer_class (drives the paginated 'results' list)."""
    disease = serializers.CharField()
    cases = serializers.IntegerField()
    lga = serializers.CharField()
    facility = serializers.CharField()
    trend = serializers.ChoiceField(choices=['INCREASING', 'DECREASING', 'STABLE'])
    alert_level = serializers.CharField(help_text="Disease.severity: CRITICAL / MODERATE / LOW")


class DiseaseTrendPointSerializer(serializers.Serializer):
    date = serializers.DateField()
    cases = serializers.IntegerField()


class LgaHeatmapRowSerializer(serializers.Serializer):
    lga = serializers.CharField()
    cases = serializers.IntegerField()


class OutbreakIndicatorSerializer(serializers.Serializer):
    disease = serializers.CharField()
    cases = serializers.IntegerField()
    alert_level = serializers.CharField()
    facilities_affected = serializers.IntegerField()


class DrugLogisticsRowSerializer(serializers.Serializer):
    facility_id = serializers.UUIDField()
    facility = serializers.CharField()
    lga = serializers.CharField()
    stock_outs = serializers.IntegerField(help_text="Count of DRUG-category items with 0 total remaining stock")
    vaccine_wastage = serializers.FloatField(help_text="Expired immunization stock / total issued, as a percentage")
    cold_chain_status = serializers.CharField(help_text="PLACEHOLDER - no cold chain monitoring model exists yet")
    tracer_drug_availability = serializers.FloatField(help_text="Approximated from all DRUG-category stock; no curated tracer-drug list model exists yet")


class DrugLogisticsReportResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    results = DrugLogisticsRowSerializer(many=True)


class HumanResourcesRowSerializer(serializers.Serializer):
    facility_id = serializers.UUIDField()
    facility = serializers.CharField()
    lga = serializers.CharField()
    nurses = serializers.IntegerField()
    chos = serializers.IntegerField(help_text="PLACEHOLDER - 'Community Health Officer' is not a distinct role in the system yet")
    chews = serializers.IntegerField()
    doctors = serializers.IntegerField()
    attendance_percent = serializers.FloatField(help_text="Approximated from login activity in the period, not biometric/manual attendance")


class HumanResourcesReportResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    results = HumanResourcesRowSerializer(many=True)


class FinancialSummaryRowSerializer(serializers.Serializer):
    facility_id = serializers.UUIDField()
    facility = serializers.CharField()
    lga = serializers.CharField()
    revenue = serializers.FloatField(help_text="PLACEHOLDER - no financial/ledger model exists yet")
    expenditure = serializers.FloatField(help_text="PLACEHOLDER - no financial/ledger model exists yet")
    bhcpf_funds = serializers.FloatField(help_text="PLACEHOLDER - no financial/ledger model exists yet")
    balance = serializers.FloatField(help_text="PLACEHOLDER - no financial/ledger model exists yet")


class FinancialSummaryReportResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    results = FinancialSummaryRowSerializer(many=True)


class ReferralAnalyticsRowSerializer(serializers.Serializer):
    facility_id = serializers.UUIDField()
    facility = serializers.CharField()
    lga = serializers.CharField()
    referrals_sent = serializers.IntegerField()
    referrals_received = serializers.IntegerField()
    ambulance_referrals = serializers.IntegerField()
    completion_rate = serializers.FloatField()
    average_referral_time_hours = serializers.FloatField(help_text="Average (updated_at - created_at) for COMPLETED referrals, in hours")


class ReferralAnalyticsReportResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    results = ReferralAnalyticsRowSerializer(many=True)


class AdverseEventsRowSerializer(serializers.Serializer):
    """Also used as AdverseEventsReportView.serializer_class (drives the paginated 'results' list)."""
    event_id = serializers.CharField()
    facility = serializers.CharField(allow_null=True, help_text="Derived from the reporting staff member's facility")
    patient = serializers.CharField()
    drug_treatment = serializers.CharField()
    adverse_event = serializers.CharField()
    severity = serializers.CharField()
    status = serializers.CharField()
    date_reported = serializers.DateField()


class AdverseEventsSummaryCardsSerializer(serializers.Serializer):
    total_adverse_events = serializers.IntegerField()
    severe_events = serializers.IntegerField()
    resolved = serializers.IntegerField()
    pending = serializers.IntegerField()
    most_common_drug = serializers.CharField(allow_null=True)
    most_common_reaction = serializers.CharField(allow_null=True)
