# core/view_nurse_reports.py
"""
Nurse Reports: facility-scoped reporting endpoints for the ward-level Nurse role.
Like OIC reports, these only ever look at the caller's own facility (request.user.facility),
never state-wide data.

There is no dedicated "batch number" link on ImmunizationRecord (only a link to the vaccine
item, not the specific dispensed batch) and no dedicated FollowUp/HealthEducation models exist
- Follow-up rows are built from FOLLOW_UP appointments plus ANC/PNC next_visit_date, and Health
Education rows are built from HealthPromotion(type=EDUCATION). Search this file for
"PLACEHOLDER" for the one field with no backing data at all.
"""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError

from appointments.models import Appointment, Vitals
from core.pagination import StandardResultsSetPagination
from core.permissions import IsNurse
from core.utils import get_validated_date_range
from immunization.models import ImmunizationRecord
from maternal_care.models import ANCVisit, PNCVisit, PNCNewbornAssessment
from nurse_chew.models import HealthPromotion

from core.serializers_nurse_reports import (
    VitalSignsRowSerializer, ImmunizationRowSerializer, PostnatalCareRowSerializer,
    MaternalCareRowSerializer, FollowUpRowSerializer, HealthEducationRowSerializer,
)

DATE_RANGE_PARAMETERS = [
    OpenApiParameter(name='start_date', description='Start date (YYYY-MM-DD). Defaults to 30 days ago.', required=False, type=str),
    OpenApiParameter(name='end_date', description='End date (YYYY-MM-DD). Defaults to today.', required=False, type=str),
]

# Clinical thresholds used for the Vital Signs summary cards. Standard adult ranges - not
# configurable anywhere in the system today, unlike SystemThreshold-backed drug stock alerts.
HYPERTENSION_SYSTOLIC = 140
HYPERTENSION_DIASTOLIC = 90
FEVER_TEMP_C = 38.0
PULSE_LOW, PULSE_HIGH = 60, 100
RESP_LOW, RESP_HIGH = 12, 20

FOLLOW_UP_DUE_WINDOW_DAYS = 7


def _get_nurse_facility(request):
    facility = request.user.facility
    if facility is None:
        raise ValidationError({"detail": "Your account has no facility assigned."})
    return facility


def _parse_bp(bp):
    try:
        sys, dia = map(int, bp.split('/'))
        return sys, dia
    except (ValueError, AttributeError):
        return None, None


def _serialize_vital(v):
    return {
        "patient": v.patient.get_full_name(),
        "date": v.created_at,
        "temperature": float(v.temperature) if v.temperature is not None else None,
        "blood_pressure": v.blood_pressure,
        "pulse": v.pulse_rate,
        "respiratory_rate": v.respiratory_rate,
        "weight": float(v.weight_kg) if v.weight_kg is not None else None,
        "height": float(v.height_cm) if v.height_cm is not None else None,
        "bmi": v.bmi,
        "recorded_by": v.created_by.get_full_name() if v.created_by else None,
    }


@extend_schema(
    tags=["Nurse Reports"],
    summary="Vital Signs Report",
    description="Paginated vitals log (temperature, BP, pulse, respiratory rate, weight, height, BMI) for the nurse's facility, with summary cards.",
    parameters=DATE_RANGE_PARAMETERS,
)
class VitalSignsReportView(generics.GenericAPIView):
    permission_classes = [IsNurse]
    pagination_class = StandardResultsSetPagination
    serializer_class = VitalSignsRowSerializer

    def get(self, request):
        facility = _get_nurse_facility(request)
        start_date, end_date = get_validated_date_range(request)
        qs = Vitals.objects.filter(
            appointment__facility=facility, created_at__date__range=[start_date, end_date]
        ).select_related('patient', 'created_by').order_by('-created_at')

        fever_cases = qs.filter(temperature__gte=FEVER_TEMP_C).count()
        abnormal_pulse_cases = qs.filter(Q(pulse_rate__lt=PULSE_LOW) | Q(pulse_rate__gt=PULSE_HIGH)).count()
        abnormal_resp_cases = qs.filter(Q(respiratory_rate__lt=RESP_LOW) | Q(respiratory_rate__gt=RESP_HIGH)).count()

        # blood_pressure is stored as a "Sys/Dia" string, not two numeric columns, so it can't
        # be filtered in the DB - fetch and parse in Python instead.
        high_bp_cases = 0
        for bp in qs.exclude(blood_pressure__isnull=True).exclude(blood_pressure__exact='').values_list('blood_pressure', flat=True):
            sys, dia = _parse_bp(bp)
            if sys is not None and (sys >= HYPERTENSION_SYSTOLIC or dia >= HYPERTENSION_DIASTOLIC):
                high_bp_cases += 1

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        rows = [_serialize_vital(v) for v in (page if page is not None else qs)]
        response = paginator.get_paginated_response(rows)
        response.data['start_date'] = start_date
        response.data['end_date'] = end_date
        response.data['summary_cards'] = {
            "total_vital_assessments": qs.count(),
            "high_blood_pressure_cases": high_bp_cases,
            "fever_cases": fever_cases,
            "abnormal_pulse_cases": abnormal_pulse_cases,
            "abnormal_respiratory_rate_cases": abnormal_resp_cases,
        }
        return response


def _fully_immunized_children_count(facility):
    """Distinct patients (all-time, not date-scoped) with a COMPLETED record for each of
    BCG, Penta 3, and Measles - the minimum set used elsewhere in this codebase
    (see ChildHealthReportView) as the core childhood immunization schedule."""
    base = ImmunizationRecord.objects.filter(facility=facility, status='COMPLETED')
    bcg = set(base.filter(vaccine_given__name__icontains='BCG').values_list('patient_id', flat=True))
    penta3 = set(base.filter(vaccine_given__name__icontains='Penta', dose_number=3).values_list('patient_id', flat=True))
    measles = set(base.filter(vaccine_given__name__icontains='Measles').values_list('patient_id', flat=True))
    return len(bcg & penta3 & measles)


def _serialize_immunization(r):
    return {
        "patient": r.patient.get_full_name(),
        "vaccine": r.vaccine_given.name,
        "dose": r.dose_number,
        "date_administered": r.date_of_visit,
        # PLACEHOLDER: ImmunizationRecord links to the vaccine item, not the specific dispensed batch.
        "batch_number": None,
        "next_due_date": r.next_due_date,
        "status": r.status,
    }


@extend_schema(
    tags=["Nurse Reports"],
    summary="Immunization Report",
    description="Paginated vaccine administration log for the nurse's facility, with summary cards.",
    parameters=DATE_RANGE_PARAMETERS,
)
class ImmunizationReportView(generics.GenericAPIView):
    permission_classes = [IsNurse]
    pagination_class = StandardResultsSetPagination
    serializer_class = ImmunizationRowSerializer

    def get(self, request):
        facility = _get_nurse_facility(request)
        start_date, end_date = get_validated_date_range(request)
        qs = ImmunizationRecord.objects.filter(
            facility=facility, date_of_visit__range=[start_date, end_date]
        ).select_related('patient', 'vaccine_given').order_by('-date_of_visit')

        by_type_rows = qs.values('vaccine_given__name').annotate(count=Count('id')).order_by('-count')
        vaccines_by_type = [{"vaccine": r['vaccine_given__name'], "count": r['count']} for r in by_type_rows]

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        rows = [_serialize_immunization(r) for r in (page if page is not None else qs)]
        response = paginator.get_paginated_response(rows)
        response.data['start_date'] = start_date
        response.data['end_date'] = end_date
        response.data['summary_cards'] = {
            "total_vaccinations": qs.count(),
            "fully_immunized_children": _fully_immunized_children_count(facility),
            "missed_appointments": qs.filter(status='MISSED').count(),
            "vaccines_administered_by_type": vaccines_by_type,
        }
        return response


def _pnc_follow_up_status(next_visit_date, today):
    if next_visit_date is None:
        return 'COMPLETE'
    if next_visit_date < today:
        return 'OVERDUE'
    if next_visit_date == today:
        return 'DUE_TODAY'
    return 'PENDING'


def _pnc_follow_ups_due_count(facility, today):
    """Mirrors the 'latest visit per episode' pattern used by MaternalAlertsView in
    nurse_chew/views.py, so a superseded visit's stale next_visit_date isn't double counted."""
    latest_ids = PNCVisit.objects.filter(
        appointment__facility=facility, next_visit_date__isnull=False, episode__status__in=['ACTIVE', 'DELIVERED']
    ).order_by('episode', '-created_at').distinct('episode').values_list('id', flat=True)
    return PNCVisit.objects.filter(id__in=latest_ids, next_visit_date__lte=today + timedelta(days=FOLLOW_UP_DUE_WINDOW_DAYS)).count()


def _serialize_pnc_visit(v, today):
    assessment = v.newborn_assessments.first()
    baby = assessment.baby.get_full_name() if assessment else None

    danger_signs = assessment.newborn_danger_signs if assessment else None
    if isinstance(danger_signs, list) and danger_signs:
        findings = ", ".join(str(s) for s in danger_signs)
    elif assessment:
        findings = "No danger signs noted"
    else:
        findings = None

    if v.referral_reason:
        complications = v.referral_reason
    elif v.outcome != 'TREATED':
        complications = v.get_outcome_display()
    elif assessment and assessment.outcome != 'HEALTHY':
        complications = assessment.get_outcome_display()
    else:
        complications = None

    return {
        "mother": v.episode.patient.get_full_name(),
        "baby": baby,
        # Approximated from MaternalCareEpisode.updated_at at the time status became DELIVERED -
        # no dedicated delivery_date field exists (same approximation used in view_oic_reports.py).
        "delivery_date": v.episode.updated_at.date() if v.episode.status == 'DELIVERED' else None,
        "visit_type": v.timing_of_visit,
        "findings": findings,
        "complications": complications,
        "follow_up_status": _pnc_follow_up_status(v.next_visit_date, today),
    }


@extend_schema(
    tags=["Nurse Reports"],
    summary="Postnatal Care Report",
    description="Paginated PNC visit log (mother, baby, delivery date, visit type, findings, complications, follow-up status) for the nurse's facility, with summary cards.",
    parameters=DATE_RANGE_PARAMETERS,
)
class PostnatalCareReportView(generics.GenericAPIView):
    permission_classes = [IsNurse]
    pagination_class = StandardResultsSetPagination
    serializer_class = PostnatalCareRowSerializer

    def get(self, request):
        facility = _get_nurse_facility(request)
        start_date, end_date = get_validated_date_range(request)
        today = timezone.now().date()

        qs = PNCVisit.objects.filter(
            appointment__facility=facility, created_at__date__range=[start_date, end_date]
        ).select_related('episode__patient', 'episode').prefetch_related('newborn_assessments__baby').order_by('-created_at')

        total = qs.count()
        mothers_reviewed = qs.values('episode__patient').distinct().count()
        babies_reviewed = PNCNewbornAssessment.objects.filter(pnc_visit__in=qs).values('baby').distinct().count()
        complications_identified = qs.filter(
            Q(outcome__in=['ADMITTED', 'REFERRED']) | Q(newborn_assessments__outcome__in=['ADMITTED', 'REFERRED'])
        ).distinct().count()

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        rows = [_serialize_pnc_visit(v, today) for v in (page if page is not None else qs)]
        response = paginator.get_paginated_response(rows)
        response.data['start_date'] = start_date
        response.data['end_date'] = end_date
        response.data['summary_cards'] = {
            "total_pnc_visits": total,
            "mothers_reviewed": mothers_reviewed,
            "babies_reviewed": babies_reviewed,
            "complications_identified": complications_identified,
            "follow_ups_due": _pnc_follow_ups_due_count(facility, today),
        }
        return response


def _hb_status(hemoglobin):
    if hemoglobin is None:
        return None
    hb = float(hemoglobin)
    if hb >= 11:
        return "Normal"
    if hb >= 7:
        return "Mild-Moderate Anemia"
    return "Severe Anemia"


@extend_schema(
    tags=["Nurse Reports"],
    summary="Maternal Care Report",
    description="Paginated ANC visit log (gestational age, BP, Hb status, IPTp dose, HIV status, risk level) for the nurse's facility, with summary cards.",
    parameters=DATE_RANGE_PARAMETERS,
)
class MaternalCareReportView(generics.GenericAPIView):
    permission_classes = [IsNurse]
    pagination_class = StandardResultsSetPagination
    serializer_class = MaternalCareRowSerializer

    def get(self, request):
        facility = _get_nurse_facility(request)
        start_date, end_date = get_validated_date_range(request)

        qs = ANCVisit.objects.filter(
            appointment__facility=facility, created_at__date__range=[start_date, end_date]
        ).select_related('episode__patient', 'episode', 'appointment').order_by('-created_at')

        total = qs.count()
        iptp_given = qs.exclude(iptp_dose_given__isnull=True).exclude(iptp_dose_given__exact='').count()

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        page_rows = list(page) if page is not None else list(qs)

        # One query for BP across the whole page instead of one Vitals lookup per row.
        appt_ids = [v.appointment_id for v in page_rows]
        bp_by_appointment = {}
        for vital in Vitals.objects.filter(appointment_id__in=appt_ids).order_by('appointment_id', '-created_at'):
            bp_by_appointment.setdefault(vital.appointment_id, vital.blood_pressure)

        def _serialize(v):
            lmp = v.episode.last_menstrual_period
            gestational_age_weeks = (v.appointment.appointment_date - lmp).days // 7 if lmp else None
            return {
                "patient": v.episode.patient.get_full_name(),
                "anc_visit": v.visit_sequence_number,
                "gestational_age_weeks": gestational_age_weeks,
                "blood_pressure": bp_by_appointment.get(v.appointment_id),
                "hb_status": _hb_status(v.hemoglobin),
                "iptp_dose": v.iptp_dose_given or None,
                "hiv_status": v.hiv_status or None,
                "risk_level": "HIGH" if (v.risk_factors and v.risk_factors.strip()) else "LOW",
            }

        rows = [_serialize(v) for v in page_rows]
        response = paginator.get_paginated_response(rows)
        response.data['start_date'] = start_date
        response.data['end_date'] = end_date
        response.data['summary_cards'] = {
            "anc_1_visits": qs.filter(visit_sequence_number=1).count(),
            "repeat_anc_visits": qs.filter(attendance_type='RETURN').count(),
            "high_risk_pregnancies": qs.exclude(risk_factors__isnull=True).exclude(risk_factors__exact='').count(),
            "iptp_coverage": round((iptp_given / total * 100), 2) if total else 0.0,
            "hiv_tests_conducted": qs.exclude(hiv_status__isnull=True).exclude(hiv_status__exact='').count(),
        }
        return response


def _followup_date_status(due_date, today):
    if due_date < today:
        return 'OVERDUE'
    if due_date == today:
        return 'DUE_TODAY'
    return 'PENDING'


def _followup_appointment_status(appt, today):
    if appt.status in ('COMPLETED', 'CANCELLED', 'NO_SHOW'):
        return 'COMPLETED'
    return _followup_date_status(appt.appointment_date, today)


@extend_schema(
    tags=["Nurse Reports"],
    summary="Follow-up Report",
    description=(
        "Paginated list of outstanding follow-ups (FOLLOW_UP-type appointments, plus ANC/PNC visits with a "
        "next_visit_date due) for the nurse's facility. Outstanding items (overdue/due today/pending) are always "
        "shown regardless of the date range; start_date/end_date only scope which already-completed follow-up "
        "appointments are included, so this behaves as a live worklist rather than a historical report."
    ),
    parameters=DATE_RANGE_PARAMETERS,
)
class FollowUpReportView(generics.GenericAPIView):
    permission_classes = [IsNurse]
    pagination_class = StandardResultsSetPagination
    serializer_class = FollowUpRowSerializer

    def get(self, request):
        facility = _get_nurse_facility(request)
        start_date, end_date = get_validated_date_range(request)
        today = timezone.now().date()

        rows = []

        appt_qs = Appointment.objects.filter(facility=facility, visit_type='FOLLOW_UP').filter(
            Q(status__in=['SCHEDULED', 'ARRIVED', 'VITALS_DONE', 'IN_CONSULTATION'])
            | Q(status__in=['COMPLETED', 'CANCELLED', 'NO_SHOW'], appointment_date__range=[start_date, end_date])
        ).select_related('patient', 'assigned_to')

        for appt in appt_qs:
            rows.append({
                "patient": appt.patient.get_full_name(),
                "reason_for_followup": appt.reason_for_visit,
                "due_date": appt.appointment_date,
                "status": _followup_appointment_status(appt, today),
                "assigned_nurse": appt.assigned_to.get_full_name() if appt.assigned_to else None,
                "outcome": appt.notes or appt.get_status_display(),
            })

        latest_anc_ids = ANCVisit.objects.filter(
            appointment__facility=facility, next_visit_date__isnull=False, episode__status='ACTIVE'
        ).order_by('episode', '-created_at').distinct('episode').values_list('id', flat=True)

        for v in ANCVisit.objects.filter(id__in=latest_anc_ids).select_related('episode__patient'):
            rows.append({
                "patient": v.episode.patient.get_full_name(),
                "reason_for_followup": f"ANC Visit {v.visit_sequence_number + 1} follow-up",
                "due_date": v.next_visit_date,
                "status": _followup_date_status(v.next_visit_date, today),
                # No dedicated assignment field exists for a not-yet-booked future ANC visit.
                "assigned_nurse": None,
                "outcome": None,
            })

        latest_pnc_ids = PNCVisit.objects.filter(
            appointment__facility=facility, next_visit_date__isnull=False, episode__status__in=['ACTIVE', 'DELIVERED']
        ).order_by('episode', '-created_at').distinct('episode').values_list('id', flat=True)

        for v in PNCVisit.objects.filter(id__in=latest_pnc_ids).select_related('episode__patient'):
            rows.append({
                "patient": v.episode.patient.get_full_name(),
                "reason_for_followup": f"PNC Visit {v.visit_sequence_number + 1} follow-up",
                "due_date": v.next_visit_date,
                "status": _followup_date_status(v.next_visit_date, today),
                "assigned_nurse": None,
                "outcome": None,
            })

        rows.sort(key=lambda r: r['due_date'])

        summary_cards = {
            "due_today": sum(1 for r in rows if r['status'] == 'DUE_TODAY'),
            "overdue": sum(1 for r in rows if r['status'] == 'OVERDUE'),
            "completed": sum(1 for r in rows if r['status'] == 'COMPLETED'),
            "pending": sum(1 for r in rows if r['status'] == 'PENDING'),
        }

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(rows, request, view=self)
        response = paginator.get_paginated_response(page if page is not None else rows)
        response.data['start_date'] = start_date
        response.data['end_date'] = end_date
        response.data['summary_cards'] = summary_cards
        return response


def _health_promotion_participants(hp):
    post_activity = getattr(hp, 'post_activity', None)
    if post_activity and post_activity.number_of_participants is not None:
        return post_activity.number_of_participants
    return hp.expected_participants


def _serialize_health_promotion(hp):
    facilitators = ", ".join(u.get_full_name() for u in hp.assigned_to.all())
    return {
        "session_date": hp.start_date,
        "topic": hp.title,
        "audience": hp.target_audience,
        "number_of_participants": _health_promotion_participants(hp),
        "facilitator": facilitators or None,
        "location": hp.location,
    }


@extend_schema(
    tags=["Nurse Reports"],
    summary="Health Education Report",
    description="Paginated log of Health Education promotion sessions (topic, audience, participants, facilitator, location) for the nurse's facility, with summary cards.",
    parameters=DATE_RANGE_PARAMETERS,
)
class HealthEducationReportView(generics.GenericAPIView):
    permission_classes = [IsNurse]
    pagination_class = StandardResultsSetPagination
    serializer_class = HealthEducationRowSerializer

    def get(self, request):
        facility = _get_nurse_facility(request)
        start_date, end_date = get_validated_date_range(request)

        qs = HealthPromotion.objects.filter(
            created_by__facility=facility, type='EDUCATION', start_date__date__range=[start_date, end_date]
        ).select_related('post_activity').prefetch_related('assigned_to').order_by('-start_date')

        completed_qs = qs.filter(status='COMPLETED')
        total_participants = sum(
            (_health_promotion_participants(hp) or 0) for hp in completed_qs.select_related('post_activity')
        )
        topic_rows = (
            qs.exclude(title__isnull=True).exclude(title__exact='')
            .values('title').annotate(count=Count('id')).order_by('-count')[:5]
        )
        most_covered_topics = [{"topic": r['title'], "count": r['count']} for r in topic_rows]

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        rows = [_serialize_health_promotion(hp) for hp in (page if page is not None else qs)]
        response = paginator.get_paginated_response(rows)
        response.data['start_date'] = start_date
        response.data['end_date'] = end_date
        response.data['summary_cards'] = {
            "sessions_conducted": completed_qs.count(),
            "total_participants": total_participants,
            "most_covered_topics": most_covered_topics,
        }
        return response
