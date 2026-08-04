# core/view_oic_reports.py
"""
OIC (Officer In Charge) Reports: facility-scoped reporting endpoints - each caller only
ever sees their own facility (request.user.facility), never state-wide data.

Fields that have no corresponding model yet (maternal mortality register, stillbirths,
low birth weight, growth monitoring/SAM, family planning, monthly report-submission
tracking, adverse-event-by-department) are returned as clearly-labelled static
placeholders - search this file for "PLACEHOLDER" to find every one. Vitamin A and
Deworming are approximated from dispensed inventory items matched by name (see
_vitamin_a_deworming_counts) rather than hard-coded, since no dedicated model exists but
the underlying dispense data does.
"""
import calendar
import re
from collections import Counter
from datetime import date

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncDate
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from adverse_events.models import AdverseEvent
from appointments.models import Appointment
from consultations.models import Consultation
from core.models import PatientProfile, User
from core.permissions import IsOfficerInCharge
from core.utils import get_validated_date_range
from immunization.models import ImmunizationRecord
from inventory.models import InventoryItem, InventoryTransaction
from maternal_care.models import ANCVisit, MaternalCareEpisode
from referrals.models import Referral
from registry.models import Disease

from core.serializers_oic_reports import (
    OicDashboardResponseSerializer, FacilitySummaryReportResponseSerializer,
    OicMaternalHealthReportResponseSerializer, OicChildHealthReportResponseSerializer,
    FamilyPlanningReportResponseSerializer, OicDiseaseSurveillanceReportResponseSerializer,
    OicReferralReportResponseSerializer, OicAdverseEventsReportResponseSerializer,
    OicMonthlyNhmisSummaryResponseSerializer,
)

DATE_RANGE_PARAMETERS = [
    OpenApiParameter(name='start_date', description='Start date (YYYY-MM-DD). Defaults to 30 days ago.', required=False, type=str),
    OpenApiParameter(name='end_date', description='End date (YYYY-MM-DD). Defaults to today.', required=False, type=str),
]

SEEN_STATUSES = ['IN_CONSULTATION', 'COMPLETED']
DESTINATION_LEVEL_LABELS = dict(Referral.DESTINATION_LEVEL_CHOICES)
VISIT_TYPE_LABELS = dict(Appointment.VISIT_TYPES)
SEX_LABELS = dict(PatientProfile.SEX_CHOICES)

# Canonical disease surveillance list requested by product, mapped to the icontains
# patterns used to match against the (shared, state-wide) registry.Disease table.
# Diseases with no match in the registry (Mpox, Polio, ARI, Diarrhoea as of writing)
# will correctly show 0 cases and in_registry=False until someone adds them there -
# that's real data, not a placeholder.
DISEASE_SURVEILLANCE_LIST = [
    ("Malaria", ["Malaria"]),
    ("Cholera", ["Cholera"]),
    ("Yellow Fever", ["Yellow Fever"]),
    ("Mpox", ["Mpox", "Monkeypox"]),
    ("Lassa Fever", ["Lassa Fever"]),
    ("Polio", ["Polio", "Poliomyelitis"]),
    ("Measles", ["Measles"]),
    ("TB", ["Tuberculosis", "TB"]),
    ("HIV", ["HIV"]),
    ("ARI", ["Acute Respiratory Infection", "ARI"]),
    ("Diarrhoea", ["Diarrhea", "Diarrhoea"]),
]


def _get_oic_facility(request):
    facility = getattr(request.user, 'facility', None)
    if not facility:
        raise ValidationError({"detail": "Your account has no facility assigned."})
    return facility


def _anc_metrics(facility, start_date, end_date):
    anc_qs = ANCVisit.objects.filter(episode__patient__facility=facility, created_at__date__range=[start_date, end_date])
    anc_total = anc_qs.count()
    anc_1 = anc_qs.filter(visit_sequence_number=1).count()
    anc_repeat = anc_qs.filter(attendance_type='RETURN').count()
    anc_4 = anc_qs.filter(visit_sequence_number__gte=4).values('episode').distinct().count()
    iptp_given = anc_qs.exclude(iptp_dose_given__isnull=True).exclude(iptp_dose_given='').count()
    return {
        "anc_1": anc_1,
        "anc_repeat": anc_repeat,
        "anc_4": anc_4,
        "iptp_coverage": round((iptp_given / anc_total * 100), 2) if anc_total else 0.0,
    }


def _delivery_count(facility, start_date, end_date):
    return MaternalCareEpisode.objects.filter(
        patient__facility=facility, status='DELIVERED', updated_at__date__range=[start_date, end_date]
    ).count()


def _neonatal_death_count(facility, start_date, end_date):
    return PatientProfile.objects.filter(
        user__facility=facility, birth_episode__isnull=False, birth_status='DEAD',
        created_at__date__range=[start_date, end_date]
    ).count()


def _immunization_breakdown(facility, start_date, end_date):
    rows = (
        ImmunizationRecord.objects.filter(facility=facility, date_of_visit__range=[start_date, end_date])
        .values('vaccine_given__name').annotate(count=Count('id')).order_by('-count')
    )
    return [{"vaccine": row['vaccine_given__name'], "count": row['count']} for row in rows]


def _vitamin_a_deworming_counts(facility, start_date, end_date):
    """Approximated from DISPENSE transactions whose inventory item name matches - no
    dedicated Vitamin A / deworming administration model exists yet."""
    dispense_qs = InventoryTransaction.objects.filter(
        transaction_type='DISPENSE', batch__item__facility=facility, created_at__date__range=[start_date, end_date]
    )
    vitamin_a = dispense_qs.filter(batch__item__name__icontains='Vitamin A').count()
    deworming = dispense_qs.filter(
        batch__item__name__iregex=r'(deworm|albendazole|mebendazole)'
    ).count()
    return vitamin_a, deworming


def _drug_stock_alerts_count(facility):
    """Counts DRUG-category items at/below their configured threshold (ABSOLUTE quantity,
    or PERCENTAGE of total ever purchased). Not date-scoped - reflects current stock."""
    items = (
        InventoryItem.objects.filter(facility=facility, inventory_category='DRUG', is_active=True)
        .annotate(total_remaining=Sum('batches__remaining_quantity'), total_initial=Sum('batches__initial_quantity'))
        .values('threshold_type', 'global_threshold', 'total_remaining', 'total_initial')
    )
    alerts = 0
    for item in items:
        remaining = item['total_remaining'] or 0
        if item['threshold_type'] == 'PERCENTAGE':
            initial = item['total_initial'] or 0
            if initial <= 0 or (remaining / initial * 100) <= item['global_threshold']:
                alerts += 1
        else:
            if remaining <= item['global_threshold']:
                alerts += 1
    return alerts


def _referral_metrics(facility, start_date, end_date):
    sent_qs = Referral.objects.filter(referring_facility=facility, created_at__date__range=[start_date, end_date])
    total = sent_qs.count()
    completed = sent_qs.filter(status='COMPLETED').count()

    avg_row = (
        sent_qs.filter(status='COMPLETED')
        .annotate(duration=ExpressionWrapper(F('updated_at') - F('created_at'), output_field=DurationField()))
        .aggregate(avg_duration=Avg('duration'))
    )
    avg_hours = round(avg_row['avg_duration'].total_seconds() / 3600, 2) if avg_row['avg_duration'] else 0.0

    destination_rows = sent_qs.values('receiving_facility__name', 'destination_level').annotate(count=Count('id')).order_by('-count')
    destinations = [
        {
            "destination": row['receiving_facility__name'] or DESTINATION_LEVEL_LABELS.get(row['destination_level'], row['destination_level']),
            "count": row['count'],
        }
        for row in destination_rows
    ]

    return {
        "total_referrals": total,
        "completed_referrals": completed,
        "emergency_referrals": sent_qs.filter(referral_type='EMERGENCY').count(),
        "ambulance_referrals": sent_qs.filter(mode_of_transportation='AMBULANCE').count(),
        "average_referral_time_hours": avg_hours,
        "referral_destinations": destinations,
    }


def _adverse_event_metrics(facility, start_date, end_date):
    qs = AdverseEvent.objects.filter(reported_by__facility=facility, created_at__date__range=[start_date, end_date])
    total = qs.count()
    severe = qs.filter(severity__in=['SEVERE', 'LIFE_THREATENING', 'FATAL']).count()
    resolved = qs.filter(status__in=['RESOLVED', 'CLOSED']).count()
    pending = qs.filter(status__in=['REPORTED', 'UNDER_REVIEW']).count()

    by_drug = [
        {"drug": row['suspected_drug__name'], "count": row['count']}
        for row in qs.values('suspected_drug__name').annotate(count=Count('id')).order_by('-count')
    ]
    by_severity = [
        {"severity": row['severity'], "count": row['count']}
        for row in qs.values('severity').annotate(count=Count('id')).order_by('-count')
    ]
    trend_rows = qs.annotate(date=TruncDate('created_at')).values('date').annotate(count=Count('id')).order_by('date')
    trend_chart = [{"date": row['date'], "count": row['count']} for row in trend_rows]

    return {
        "facility_summary": {"total_adverse_events": total, "severe_events": severe, "resolved": resolved, "pending": pending},
        # PLACEHOLDER: AdverseEvent has no department field, and reported_by's department
        # membership is a many-valued M2M, so there is no reliable single department per event.
        "by_department": [],
        "by_drug": by_drug,
        "by_severity": by_severity,
        "trend_chart": trend_chart,
    }


def _word_boundary_q(field_lookup, patterns):
    """Builds an OR'd Q using Postgres word-boundary regex (\\y) rather than icontains,
    since short acronym patterns like "ARI"/"TB"/"HIV" would otherwise false-match as a
    bare substring of unrelated names (e.g. icontains 'ARI' matches 'Malaria')."""
    q = Q()
    for pattern in patterns:
        q |= Q(**{f"{field_lookup}__iregex": rf"\y{re.escape(pattern)}\y"})
    return q


def _disease_surveillance_rows(facility, start_date, end_date):
    rows = []
    for label, patterns in DISEASE_SURVEILLANCE_LIST:
        matched_disease = Disease.objects.filter(_word_boundary_q('name', patterns)).first()

        cases = 0
        if matched_disease:
            cases = Consultation.objects.filter(
                _word_boundary_q('diagnosed_disease__name', patterns),
                appointment__facility=facility, created_at__date__range=[start_date, end_date]
            ).count()

        severity = matched_disease.severity if matched_disease else None
        rows.append({
            "disease": label,
            "cases": cases,
            "severity": severity,
            "is_epidemic_prone": severity == 'CRITICAL',
            "in_registry": matched_disease is not None,
        })
    return rows


def _patient_attendance(facility, start_date, end_date):
    apt_qs = Appointment.objects.filter(facility=facility, appointment_date__range=[start_date, end_date])
    trend_rows = apt_qs.annotate(date=TruncDate('appointment_date')).values('date').annotate(count=Count('id')).order_by('date')
    return {
        "total_appointments": apt_qs.count(),
        "trend": [{"date": row['date'], "count": row['count']} for row in trend_rows],
    }


def _gender_distribution(facility):
    rows = PatientProfile.objects.filter(user__facility=facility).values('sex').annotate(count=Count('id'))
    return [{"sex": row['sex'], "label": SEX_LABELS.get(row['sex'], row['sex']), "count": row['count']} for row in rows]


def _age_group_for_dob(dob, today):
    """Mirrors PatientProfile.age_group, but works off a plain date value instead of a
    model instance - instantiating BaseModel subclasses via .only()/.values() triggers
    an eager full-field touch in BaseModel.__init__ (for audit logging) that recurses
    badly against deferred fields, so we deliberately never build model instances here."""
    if not dob:
        return "Unknown"
    delta_days = (today - dob).days
    age_years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if delta_days <= 28:
        return "Neonate"
    elif age_years < 1:
        return "Infant"
    elif 1 <= age_years <= 3:
        return "Toddler"
    elif 4 <= age_years <= 12:
        return "Child"
    elif 13 <= age_years <= 17:
        return "Adolescent"
    elif 18 <= age_years <= 64:
        return "Adult"
    else:
        return "Senior"


def _age_distribution(facility):
    today = date.today()
    dobs = PatientProfile.objects.filter(user__facility=facility).values_list('date_of_birth', flat=True)
    counts = Counter(_age_group_for_dob(dob, today) for dob in dobs)
    return [{"age_group": group, "count": count} for group, count in counts.items()]


def _top_diseases(facility, start_date, end_date, limit=5):
    qs = Consultation.objects.filter(
        appointment__facility=facility, created_at__date__range=[start_date, end_date], diagnosed_disease__isnull=False
    )
    total = qs.count()
    rows = qs.values('diagnosed_disease__name').annotate(count=Count('id')).order_by('-count')[:limit]
    return [
        {"disease": row['diagnosed_disease__name'], "count": row['count'], "percentage": round(row['count'] / total * 100, 2) if total else 0.0}
        for row in rows
    ]


def _service_utilization(facility, start_date, end_date):
    rows = (
        Appointment.objects.filter(facility=facility, appointment_date__range=[start_date, end_date])
        .values('visit_type').annotate(count=Count('id')).order_by('-count')
    )
    return [{"visit_type": row['visit_type'], "label": VISIT_TYPE_LABELS.get(row['visit_type'], row['visit_type']), "count": row['count']} for row in rows]


@extend_schema(
    tags=["OIC Reports"],
    summary="OIC Dashboard Cards",
    description="Facility-scoped dashboard KPI tiles for the caller's own facility.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=OicDashboardResponseSerializer,
)
class OicDashboardView(APIView):
    permission_classes = [IsOfficerInCharge]

    def get(self, request):
        facility = _get_oic_facility(request)
        start_date, end_date = get_validated_date_range(request)

        total_patients = User.objects.filter(facility=facility, role='PATIENT', is_active=True).count()
        anc = _anc_metrics(facility, start_date, end_date)
        deliveries = _delivery_count(facility, start_date, end_date)
        immunizations = ImmunizationRecord.objects.filter(facility=facility, date_of_visit__range=[start_date, end_date]).count()
        referrals = Referral.objects.filter(referring_facility=facility, created_at__date__range=[start_date, end_date]).count()

        return Response({
            "start_date": start_date,
            "end_date": end_date,
            "total_patients": total_patients,
            "anc_attendance": anc['anc_1'] + anc['anc_repeat'],
            "deliveries": deliveries,
            "immunizations": immunizations,
            "referrals": referrals,
            "drug_stock_alerts": _drug_stock_alerts_count(facility),
            # PLACEHOLDER: no maternal mortality register exists yet.
            "maternal_deaths": 0,
            "neonatal_deaths": _neonatal_death_count(facility, start_date, end_date),
            # PLACEHOLDER: no facility monthly-report-submission tracking model exists yet.
            "monthly_reporting_status": {"month": end_date.strftime('%Y-%m'), "status": "NOT_TRACKED"},
        })


@extend_schema(
    tags=["OIC Reports"],
    summary="Facility Summary Report",
    description="Patient attendance, gender/age distribution, top diseases, referral statistics, and service utilization for the caller's own facility.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=FacilitySummaryReportResponseSerializer,
)
class FacilitySummaryReportView(APIView):
    permission_classes = [IsOfficerInCharge]

    def get(self, request):
        facility = _get_oic_facility(request)
        start_date, end_date = get_validated_date_range(request)

        sent = Referral.objects.filter(referring_facility=facility, created_at__date__range=[start_date, end_date])
        received = Referral.objects.filter(receiving_facility=facility, created_at__date__range=[start_date, end_date])
        sent_count = sent.count()
        completed_count = sent.filter(status='COMPLETED').count()

        return Response({
            "start_date": start_date,
            "end_date": end_date,
            "patient_attendance": _patient_attendance(facility, start_date, end_date),
            "gender_distribution": _gender_distribution(facility),
            "age_distribution": _age_distribution(facility),
            "top_diseases": _top_diseases(facility, start_date, end_date),
            "referral_statistics": {
                "sent": sent_count,
                "received": received.count(),
                "completed": completed_count,
                "completion_rate": round(completed_count / sent_count * 100, 2) if sent_count else 0.0,
            },
            "service_utilization": _service_utilization(facility, start_date, end_date),
        })


@extend_schema(
    tags=["OIC Reports"],
    summary="Maternal Health Report",
    description="ANC1/ANC Repeat/ANC4, deliveries, stillbirths, low birth weight, maternal/neonatal deaths, and IPTp coverage for the caller's own facility.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=OicMaternalHealthReportResponseSerializer,
)
class OicMaternalHealthReportView(APIView):
    permission_classes = [IsOfficerInCharge]

    def get(self, request):
        facility = _get_oic_facility(request)
        start_date, end_date = get_validated_date_range(request)
        anc = _anc_metrics(facility, start_date, end_date)

        return Response({
            "start_date": start_date,
            "end_date": end_date,
            "anc_1": anc['anc_1'],
            "anc_repeat": anc['anc_repeat'],
            "anc_4": anc['anc_4'],
            "deliveries": _delivery_count(facility, start_date, end_date),
            # PLACEHOLDER: no stillbirth field/model exists yet.
            "stillbirths": 0,
            # PLACEHOLDER: no birth-weight field/model exists yet.
            "low_birth_weight": 0,
            # PLACEHOLDER: no maternal mortality register exists yet.
            "maternal_deaths": 0,
            "neonatal_deaths": _neonatal_death_count(facility, start_date, end_date),
            "iptp_coverage": anc['iptp_coverage'],
        })


@extend_schema(
    tags=["OIC Reports"],
    summary="Child Health Report",
    description="Immunization coverage by vaccine, growth monitoring, SAM, Vitamin A, and deworming for the caller's own facility.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=OicChildHealthReportResponseSerializer,
)
class OicChildHealthReportView(APIView):
    permission_classes = [IsOfficerInCharge]

    def get(self, request):
        facility = _get_oic_facility(request)
        start_date, end_date = get_validated_date_range(request)
        vitamin_a, deworming = _vitamin_a_deworming_counts(facility, start_date, end_date)

        return Response({
            "start_date": start_date,
            "end_date": end_date,
            "immunization_coverage": _immunization_breakdown(facility, start_date, end_date),
            # PLACEHOLDER: no growth-monitoring model exists yet.
            "growth_monitoring": 0,
            # PLACEHOLDER: no malnutrition/SAM model exists yet.
            "sam": 0,
            "vitamin_a": vitamin_a,
            "deworming": deworming,
        })


@extend_schema(
    tags=["OIC Reports"],
    summary="Family Planning Report",
    description="PLACEHOLDER - no Family Planning model exists anywhere in the system yet. All figures are static until that module is built.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=FamilyPlanningReportResponseSerializer,
)
class FamilyPlanningReportView(APIView):
    permission_classes = [IsOfficerInCharge]

    def get(self, request):
        _get_oic_facility(request)
        start_date, end_date = get_validated_date_range(request)

        # PLACEHOLDER: no family planning model exists anywhere in the system yet.
        return Response({
            "start_date": start_date,
            "end_date": end_date,
            "new_clients": 0,
            "repeat_clients": 0,
            "methods_used": [],
            "commodity_distribution": [],
            "counselling_sessions": 0,
        })


@extend_schema(
    tags=["OIC Reports"],
    summary="Disease Surveillance Report",
    description="Fixed list of 11 tracked diseases with case counts for the caller's own facility. Epidemic-prone diseases (severity=CRITICAL in the disease registry) are auto-flagged via is_epidemic_prone.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=OicDiseaseSurveillanceReportResponseSerializer,
)
class OicDiseaseSurveillanceReportView(APIView):
    permission_classes = [IsOfficerInCharge]

    def get(self, request):
        facility = _get_oic_facility(request)
        start_date, end_date = get_validated_date_range(request)

        return Response({
            "start_date": start_date,
            "end_date": end_date,
            "results": _disease_surveillance_rows(facility, start_date, end_date),
        })


@extend_schema(
    tags=["OIC Reports"],
    summary="Referral Report",
    description="Total/completed/emergency/ambulance referrals, average referral time, and referral destinations, for referrals sent out from the caller's own facility.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=OicReferralReportResponseSerializer,
)
class OicReferralReportView(APIView):
    permission_classes = [IsOfficerInCharge]

    def get(self, request):
        facility = _get_oic_facility(request)
        start_date, end_date = get_validated_date_range(request)

        return Response({
            "start_date": start_date,
            "end_date": end_date,
            **_referral_metrics(facility, start_date, end_date),
        })


@extend_schema(
    tags=["OIC Reports"],
    summary="Adverse Events Report",
    description="Facility summary, drug/severity breakdowns, and a trend chart for adverse events reported at the caller's own facility.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=OicAdverseEventsReportResponseSerializer,
)
class OicAdverseEventsReportView(APIView):
    permission_classes = [IsOfficerInCharge]

    def get(self, request):
        facility = _get_oic_facility(request)
        start_date, end_date = get_validated_date_range(request)

        return Response({
            "start_date": start_date,
            "end_date": end_date,
            **_adverse_event_metrics(facility, start_date, end_date),
        })


@extend_schema(
    tags=["OIC Reports"],
    summary="Monthly NHMIS Summary",
    description="Automatically aggregates every monthly indicator above (maternal health, child health, family planning, disease surveillance, referrals, adverse events, drug logistics) for the caller's own facility, for a single calendar month.",
    parameters=[
        OpenApiParameter(name='month', description="Month to summarize, as YYYY-MM. Defaults to the current month.", required=False, type=str),
    ],
    responses=OicMonthlyNhmisSummaryResponseSerializer,
)
class OicMonthlyNhmisSummaryView(APIView):
    permission_classes = [IsOfficerInCharge]

    def get(self, request):
        facility = _get_oic_facility(request)

        month_str = request.query_params.get('month')
        if month_str:
            try:
                year, month = (int(part) for part in month_str.split('-'))
                start_date = date(year, month, 1)
            except (ValueError, TypeError):
                raise ValidationError({"detail": "month must be in YYYY-MM format."})
        else:
            today = date.today()
            start_date = date(today.year, today.month, 1)

        last_day = calendar.monthrange(start_date.year, start_date.month)[1]
        end_date = min(date(start_date.year, start_date.month, last_day), date.today())

        anc = _anc_metrics(facility, start_date, end_date)
        vitamin_a, deworming = _vitamin_a_deworming_counts(facility, start_date, end_date)

        return Response({
            "month": start_date.strftime('%Y-%m'),
            "start_date": start_date,
            "end_date": end_date,
            "facility": {"id": facility.id, "name": facility.name, "code": facility.code, "lga": facility.lga},
            "maternal_health": {
                "anc_1": anc['anc_1'],
                "anc_repeat": anc['anc_repeat'],
                "anc_4": anc['anc_4'],
                "deliveries": _delivery_count(facility, start_date, end_date),
                "stillbirths": 0,
                "low_birth_weight": 0,
                "maternal_deaths": 0,
                "neonatal_deaths": _neonatal_death_count(facility, start_date, end_date),
                "iptp_coverage": anc['iptp_coverage'],
            },
            "child_health": {
                "immunization_coverage": _immunization_breakdown(facility, start_date, end_date),
                "growth_monitoring": 0,
                "sam": 0,
                "vitamin_a": vitamin_a,
                "deworming": deworming,
            },
            "family_planning": {
                "new_clients": 0,
                "repeat_clients": 0,
                "methods_used": [],
                "commodity_distribution": [],
                "counselling_sessions": 0,
            },
            "disease_surveillance": {"results": _disease_surveillance_rows(facility, start_date, end_date)},
            "referrals": _referral_metrics(facility, start_date, end_date),
            "adverse_events": _adverse_event_metrics(facility, start_date, end_date),
            "drug_logistics": {"drug_stock_alerts": _drug_stock_alerts_count(facility)},
        })
