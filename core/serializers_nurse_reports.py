# core/serializers_nurse_reports.py
"""Response serializers for core/view_nurse_reports.py - used purely so drf-spectacular
can document these APIViews; the views build their response dicts by hand and don't call
these serializers at runtime."""
from rest_framework import serializers


class VitalSignsRowSerializer(serializers.Serializer):
    """Also used as VitalSignsReportView.serializer_class (drives the paginated 'results' list)."""
    patient = serializers.CharField()
    date = serializers.DateTimeField()
    temperature = serializers.FloatField(allow_null=True, help_text="Celsius (°C)")
    blood_pressure = serializers.CharField(allow_null=True, help_text="Systolic/Diastolic, e.g. 120/80")
    pulse = serializers.IntegerField(allow_null=True, help_text="BPM")
    respiratory_rate = serializers.IntegerField(allow_null=True, help_text="Breaths per minute")
    weight = serializers.FloatField(allow_null=True, help_text="kg")
    height = serializers.FloatField(allow_null=True, help_text="cm")
    bmi = serializers.FloatField(allow_null=True)
    recorded_by = serializers.CharField(allow_null=True)


class VitalSignsSummaryCardsSerializer(serializers.Serializer):
    total_vital_assessments = serializers.IntegerField()
    high_blood_pressure_cases = serializers.IntegerField(help_text="Systolic >= 140 or Diastolic >= 90")
    fever_cases = serializers.IntegerField(help_text="Temperature >= 38.0°C")
    abnormal_pulse_cases = serializers.IntegerField(help_text="Pulse < 60 or > 100 BPM")
    abnormal_respiratory_rate_cases = serializers.IntegerField(help_text="Respiratory rate < 12 or > 20 breaths/min")


class ImmunizationRowSerializer(serializers.Serializer):
    """Also used as ImmunizationReportView.serializer_class (drives the paginated 'results' list)."""
    patient = serializers.CharField()
    vaccine = serializers.CharField()
    dose = serializers.IntegerField()
    date_administered = serializers.DateField()
    batch_number = serializers.CharField(allow_null=True, help_text="PLACEHOLDER - ImmunizationRecord has no batch-level link, only the vaccine item")
    next_due_date = serializers.DateField(allow_null=True)
    status = serializers.CharField()


class VaccineTypeCountSerializer(serializers.Serializer):
    vaccine = serializers.CharField()
    count = serializers.IntegerField()


class ImmunizationSummaryCardsSerializer(serializers.Serializer):
    total_vaccinations = serializers.IntegerField()
    fully_immunized_children = serializers.IntegerField(
        help_text="All-time (not date-scoped) count of distinct patients at this facility with a COMPLETED record for BCG, Penta 3, and Measles"
    )
    missed_appointments = serializers.IntegerField(help_text="ImmunizationRecord.status = MISSED, within the date range")
    vaccines_administered_by_type = VaccineTypeCountSerializer(many=True)


class PostnatalCareRowSerializer(serializers.Serializer):
    """Also used as PostnatalCareReportView.serializer_class (drives the paginated 'results' list)."""
    mother = serializers.CharField()
    baby = serializers.CharField(allow_null=True, help_text="Null if no newborn assessment has been linked to this PNC visit yet")
    delivery_date = serializers.DateField(allow_null=True, help_text="Approximated from MaternalCareEpisode.updated_at at the time status became DELIVERED - no dedicated delivery_date field exists")
    visit_type = serializers.CharField(help_text="PNCVisit.timing_of_visit, e.g. Within 24h / 6 Days / 6 Weeks")
    findings = serializers.CharField(allow_null=True)
    complications = serializers.CharField(allow_null=True)
    follow_up_status = serializers.CharField(help_text="OVERDUE / DUE_TODAY / PENDING / COMPLETE, derived from next_visit_date")


class PostnatalCareSummaryCardsSerializer(serializers.Serializer):
    total_pnc_visits = serializers.IntegerField()
    mothers_reviewed = serializers.IntegerField(help_text="Distinct mothers across the visits in range")
    babies_reviewed = serializers.IntegerField(help_text="Distinct babies with a newborn assessment linked to a visit in range")
    complications_identified = serializers.IntegerField(help_text="Visits where the mother's outcome != TREATED or the linked newborn's outcome != HEALTHY")
    follow_ups_due = serializers.IntegerField(help_text="Visits with next_visit_date within the next 7 days or overdue, not date-range scoped")


class MaternalCareRowSerializer(serializers.Serializer):
    """Also used as MaternalCareReportView.serializer_class (drives the paginated 'results' list)."""
    patient = serializers.CharField()
    anc_visit = serializers.IntegerField(help_text="visit_sequence_number")
    gestational_age_weeks = serializers.IntegerField(allow_null=True, help_text="Computed from the episode's last_menstrual_period; null if LMP wasn't recorded")
    blood_pressure = serializers.CharField(allow_null=True, help_text="From the Vitals record linked to the same appointment, if one exists")
    hb_status = serializers.CharField(allow_null=True, help_text="Normal (>=11 g/dL) / Mild-Moderate Anemia (7-10.9) / Severe Anemia (<7), derived from ANCVisit.hemoglobin")
    iptp_dose = serializers.CharField(allow_null=True)
    hiv_status = serializers.CharField(allow_null=True)
    risk_level = serializers.CharField(help_text="HIGH if risk_factors is recorded, else LOW - there is no dedicated risk-level field")


class MaternalCareSummaryCardsSerializer(serializers.Serializer):
    anc_1_visits = serializers.IntegerField()
    repeat_anc_visits = serializers.IntegerField(help_text="attendance_type = RETURN")
    high_risk_pregnancies = serializers.IntegerField(help_text="Visits with a non-empty risk_factors note")
    iptp_coverage = serializers.FloatField(help_text="Percentage of visits with an IPTp dose recorded")
    hiv_tests_conducted = serializers.IntegerField(help_text="Visits with a non-empty hiv_status")


class FollowUpRowSerializer(serializers.Serializer):
    """Also used as FollowUpReportView.serializer_class (drives the paginated 'results' list)."""
    patient = serializers.CharField()
    reason_for_followup = serializers.CharField()
    due_date = serializers.DateField()
    status = serializers.ChoiceField(choices=['OVERDUE', 'DUE_TODAY', 'PENDING', 'COMPLETED'])
    assigned_nurse = serializers.CharField(allow_null=True, help_text="Null for ANC/PNC-derived follow-ups, which have no dedicated assignment field")
    outcome = serializers.CharField(allow_null=True)


class FollowUpSummaryCardsSerializer(serializers.Serializer):
    due_today = serializers.IntegerField()
    overdue = serializers.IntegerField()
    completed = serializers.IntegerField(help_text="Completed follow-up appointments within the date range")
    pending = serializers.IntegerField()


class HealthEducationRowSerializer(serializers.Serializer):
    """Also used as HealthEducationReportView.serializer_class (drives the paginated 'results' list)."""
    session_date = serializers.DateTimeField(allow_null=True)
    topic = serializers.CharField(allow_null=True, help_text="HealthPromotion.title - there is no separate 'topic' field")
    audience = serializers.CharField(allow_null=True)
    number_of_participants = serializers.IntegerField(
        allow_null=True,
        help_text="Actual attendance from the linked PostActivity if submitted, otherwise the expected_participants estimate"
    )
    facilitator = serializers.CharField(allow_null=True)
    location = serializers.CharField(allow_null=True)


class TopicCountSerializer(serializers.Serializer):
    topic = serializers.CharField()
    count = serializers.IntegerField()


class HealthEducationSummaryCardsSerializer(serializers.Serializer):
    sessions_conducted = serializers.IntegerField(help_text="type=EDUCATION, status=COMPLETED, within the date range")
    total_participants = serializers.IntegerField()
    most_covered_topics = TopicCountSerializer(many=True)
