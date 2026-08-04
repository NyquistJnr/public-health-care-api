# core/serializers_oic_reports.py
"""Response serializers for core/view_oic_reports.py - used purely so drf-spectacular can
document these APIViews; the views build their response dicts by hand and don't call
these serializers at runtime. "Body" serializers hold the fields shared between a
standalone report endpoint and its nested section inside OicMonthlyNhmisSummaryView."""
from rest_framework import serializers


class MonthlyReportingStatusSerializer(serializers.Serializer):
    month = serializers.CharField()
    status = serializers.CharField(help_text="PLACEHOLDER - no facility monthly-report-submission tracking model exists yet")


class OicDashboardResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    total_patients = serializers.IntegerField(help_text="All-time active patients registered at this facility (not date-scoped)")
    anc_attendance = serializers.IntegerField(help_text="ANC1 + ANC repeat visits in the period")
    deliveries = serializers.IntegerField()
    immunizations = serializers.IntegerField()
    referrals = serializers.IntegerField(help_text="Referrals sent out from this facility in the period")
    drug_stock_alerts = serializers.IntegerField(help_text="Count of DRUG items at/below their configured threshold (current snapshot, not date-scoped)")
    maternal_deaths = serializers.IntegerField(help_text="PLACEHOLDER - no maternal mortality register exists yet")
    neonatal_deaths = serializers.IntegerField()
    monthly_reporting_status = MonthlyReportingStatusSerializer()


class AttendanceTrendPointSerializer(serializers.Serializer):
    date = serializers.DateField()
    count = serializers.IntegerField()


class PatientAttendanceSerializer(serializers.Serializer):
    total_appointments = serializers.IntegerField()
    trend = AttendanceTrendPointSerializer(many=True)


class GenderDistributionRowSerializer(serializers.Serializer):
    sex = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()


class AgeDistributionRowSerializer(serializers.Serializer):
    age_group = serializers.CharField(help_text="Neonate / Infant / Toddler / Child / Adolescent / Adult / Senior")
    count = serializers.IntegerField()


class TopDiseaseRowSerializer(serializers.Serializer):
    disease = serializers.CharField()
    count = serializers.IntegerField()
    percentage = serializers.FloatField()


class ReferralStatisticsSerializer(serializers.Serializer):
    sent = serializers.IntegerField()
    received = serializers.IntegerField()
    completed = serializers.IntegerField()
    completion_rate = serializers.FloatField()


class ServiceUtilizationRowSerializer(serializers.Serializer):
    visit_type = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()


class FacilitySummaryReportResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    patient_attendance = PatientAttendanceSerializer()
    gender_distribution = GenderDistributionRowSerializer(many=True)
    age_distribution = AgeDistributionRowSerializer(many=True)
    top_diseases = TopDiseaseRowSerializer(many=True)
    referral_statistics = ReferralStatisticsSerializer()
    service_utilization = ServiceUtilizationRowSerializer(many=True)


class MaternalHealthBodySerializer(serializers.Serializer):
    anc_1 = serializers.IntegerField()
    anc_repeat = serializers.IntegerField()
    anc_4 = serializers.IntegerField()
    deliveries = serializers.IntegerField()
    stillbirths = serializers.IntegerField(help_text="PLACEHOLDER - no stillbirth field/model exists yet")
    low_birth_weight = serializers.IntegerField(help_text="PLACEHOLDER - no birth-weight field/model exists yet")
    maternal_deaths = serializers.IntegerField(help_text="PLACEHOLDER - no maternal mortality register exists yet")
    neonatal_deaths = serializers.IntegerField()
    iptp_coverage = serializers.FloatField()


class OicMaternalHealthReportResponseSerializer(MaternalHealthBodySerializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class ImmunizationCoverageRowSerializer(serializers.Serializer):
    vaccine = serializers.CharField()
    count = serializers.IntegerField()


class ChildHealthBodySerializer(serializers.Serializer):
    immunization_coverage = ImmunizationCoverageRowSerializer(many=True)
    growth_monitoring = serializers.IntegerField(help_text="PLACEHOLDER - no growth-monitoring model exists yet")
    sam = serializers.IntegerField(help_text="PLACEHOLDER - no malnutrition/SAM model exists yet")
    vitamin_a = serializers.IntegerField(help_text="Approximated from dispensed inventory items matching 'Vitamin A' by name")
    deworming = serializers.IntegerField(help_text="Approximated from dispensed inventory items matching deworming drug names")


class OicChildHealthReportResponseSerializer(ChildHealthBodySerializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class FamilyPlanningBodySerializer(serializers.Serializer):
    new_clients = serializers.IntegerField(help_text="PLACEHOLDER - no Family Planning model exists yet")
    repeat_clients = serializers.IntegerField(help_text="PLACEHOLDER - no Family Planning model exists yet")
    methods_used = serializers.ListField(child=serializers.DictField(), help_text="PLACEHOLDER - no Family Planning model exists yet")
    commodity_distribution = serializers.ListField(child=serializers.DictField(), help_text="PLACEHOLDER - no Family Planning model exists yet")
    counselling_sessions = serializers.IntegerField(help_text="PLACEHOLDER - no Family Planning model exists yet")


class FamilyPlanningReportResponseSerializer(FamilyPlanningBodySerializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class OicDiseaseSurveillanceRowSerializer(serializers.Serializer):
    disease = serializers.CharField()
    cases = serializers.IntegerField()
    severity = serializers.CharField(allow_null=True, help_text="CRITICAL / MODERATE / LOW, or null if this disease isn't in the registry yet")
    is_epidemic_prone = serializers.BooleanField(help_text="True when severity=CRITICAL")
    in_registry = serializers.BooleanField(help_text="False means this disease has never been added to registry.Disease - cases will always be 0 until it is")


class DiseaseSurveillanceBodySerializer(serializers.Serializer):
    results = OicDiseaseSurveillanceRowSerializer(many=True)


class OicDiseaseSurveillanceReportResponseSerializer(DiseaseSurveillanceBodySerializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class ReferralDestinationRowSerializer(serializers.Serializer):
    destination = serializers.CharField(help_text="Receiving facility name, or destination level label if no specific facility was recorded")
    count = serializers.IntegerField()


class ReferralBodySerializer(serializers.Serializer):
    total_referrals = serializers.IntegerField()
    completed_referrals = serializers.IntegerField()
    emergency_referrals = serializers.IntegerField()
    ambulance_referrals = serializers.IntegerField()
    average_referral_time_hours = serializers.FloatField()
    referral_destinations = ReferralDestinationRowSerializer(many=True)


class OicReferralReportResponseSerializer(ReferralBodySerializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class AdverseEventsFacilitySummarySerializer(serializers.Serializer):
    total_adverse_events = serializers.IntegerField()
    severe_events = serializers.IntegerField()
    resolved = serializers.IntegerField()
    pending = serializers.IntegerField()


class AdverseEventsByDrugRowSerializer(serializers.Serializer):
    drug = serializers.CharField()
    count = serializers.IntegerField()


class AdverseEventsBySeverityRowSerializer(serializers.Serializer):
    severity = serializers.CharField()
    count = serializers.IntegerField()


class AdverseEventsTrendPointSerializer(serializers.Serializer):
    date = serializers.DateField()
    count = serializers.IntegerField()


class AdverseEventsBodySerializer(serializers.Serializer):
    facility_summary = AdverseEventsFacilitySummarySerializer()
    by_department = serializers.ListField(child=serializers.DictField(), help_text="PLACEHOLDER - AdverseEvent has no reliable single-department relation")
    by_drug = AdverseEventsByDrugRowSerializer(many=True)
    by_severity = AdverseEventsBySeverityRowSerializer(many=True)
    trend_chart = AdverseEventsTrendPointSerializer(many=True)


class OicAdverseEventsReportResponseSerializer(AdverseEventsBodySerializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class NhmisFacilitySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    code = serializers.CharField()
    lga = serializers.CharField()


class NhmisDrugLogisticsSerializer(serializers.Serializer):
    drug_stock_alerts = serializers.IntegerField()


class OicMonthlyNhmisSummaryResponseSerializer(serializers.Serializer):
    month = serializers.CharField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    facility = NhmisFacilitySerializer()
    maternal_health = MaternalHealthBodySerializer()
    child_health = ChildHealthBodySerializer()
    family_planning = FamilyPlanningBodySerializer()
    disease_surveillance = DiseaseSurveillanceBodySerializer()
    referrals = ReferralBodySerializer()
    adverse_events = AdverseEventsBodySerializer()
    drug_logistics = NhmisDrugLogisticsSerializer()
