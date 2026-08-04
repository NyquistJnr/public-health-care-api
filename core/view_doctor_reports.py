# core/view_doctor_reports.py
"""
Doctor Reports: personal, patient-care-focused reporting endpoints - each caller only ever
sees their own consultations, referrals, prescriptions, and reported adverse events
(request.user), never facility- or state-wide data.

Consultation has no dedicated "outcome" field, so consultation_outcome is derived from the
underlying appointment's status plus whether the doctor referred that same appointment out.
Clinical Outcome Report's Recovered/Admitted/Transferred/Deaths have no backing model at all
(PatientProfile.birth_status only tracks newborn birth outcomes, not general adult clinical
outcomes) and are returned as clearly-labelled static placeholders - search this file for
"PLACEHOLDER" to find them. Referred is real data (Referral model).
"""
from collections import Counter
from datetime import date

from django.db.models import Count, Q
from django.db.models.functions import Coalesce
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from adverse_events.models import AdverseEvent
from appointments.models import Appointment
from consultations.models import Consultation
from core.pagination import StandardResultsSetPagination
from core.permissions import IsDoctor
from core.utils import get_validated_date_range, word_boundary_q
from prescriptions.models import PrescriptionItem
from referrals.models import Referral

from core.serializers_doctor_reports import (
    ConsultationReportResponseSerializer, DiseaseMorbidityReportResponseSerializer,
    DoctorReferralRowSerializer, DoctorAdverseEventRowSerializer,
    ClinicalOutcomeReportResponseSerializer,
)

DATE_RANGE_PARAMETERS = [
    OpenApiParameter(name='start_date', description='Start date (YYYY-MM-DD). Defaults to 30 days ago.', required=False, type=str),
    OpenApiParameter(name='end_date', description='End date (YYYY-MM-DD). Defaults to today.', required=False, type=str),
]

REFERRAL_STATUS_LABELS = dict(Referral.STATUS_CHOICES)
APPOINTMENT_STATUS_LABELS = dict(Appointment.STATUS_CHOICES)

# Canonical disease morbidity list requested by product. Matched against both the doctor's
# free-text primary_diagnosis and the structured diagnosed_disease link, since consultations
# don't consistently use the registry link.
DISEASE_MORBIDITY_LIST = [
    ("Malaria", ["Malaria"]),
    ("ARI", ["Acute Respiratory Infection", "ARI"]),
    ("Diarrhoea", ["Diarrhea", "Diarrhoea"]),
    ("Hypertension", ["Hypertension"]),
    ("Diabetes", ["Diabetes"]),
    ("Asthma", ["Asthma"]),
    ("HIV", ["HIV"]),
    ("TB", ["Tuberculosis", "TB"]),
    ("Mental Health", ["Mental Health", "Depression", "Anxiety", "Psychosis", "Schizophrenia", "Bipolar"]),
]


def _diagnosis_match_q(patterns):
    q = Q()
    for pattern in patterns:
        field_q = word_boundary_q('primary_diagnosis', [pattern]) | word_boundary_q('diagnosed_disease__name', [pattern])
        q |= field_q
    return q


def _doctor_diagnosis_distribution(doctor, start_date, end_date, limit=10):
    rows = (
        Consultation.objects.filter(doctor=doctor, created_at__date__range=[start_date, end_date])
        .exclude(primary_diagnosis='')
        .values('primary_diagnosis').annotate(count=Count('id')).order_by('-count')[:limit]
    )
    return [{"diagnosis": row['primary_diagnosis'], "count": row['count']} for row in rows]


def _doctor_treatment_distribution(doctor, start_date, end_date, limit=10):
    rows = (
        PrescriptionItem.objects.filter(prescription__prescribed_by=doctor, created_at__date__range=[start_date, end_date])
        .annotate(treatment=Coalesce('inventory_item__name', 'custom_drug_name'))
        .values('treatment').annotate(count=Count('id')).order_by('-count')[:limit]
    )
    return [{"treatment": row['treatment'] or 'Unspecified', "count": row['count']} for row in rows]


def _doctor_referral_status_distribution(doctor, start_date, end_date):
    rows = (
        Referral.objects.filter(referred_by=doctor, created_at__date__range=[start_date, end_date])
        .values('status').annotate(count=Count('id')).order_by('-count')
    )
    return [{"status": row['status'], "label": REFERRAL_STATUS_LABELS.get(row['status'], row['status']), "count": row['count']} for row in rows]


def _doctor_consultation_outcome_distribution(doctor, start_date, end_date):
    qs = Consultation.objects.filter(doctor=doctor, created_at__date__range=[start_date, end_date])
    referred_appointment_ids = set(
        Referral.objects.filter(referred_by=doctor, created_at__date__range=[start_date, end_date]).values_list('appointment_id', flat=True)
    )

    counts = Counter()
    for appointment_id, apt_status in qs.values_list('appointment_id', 'appointment__status'):
        if appointment_id in referred_appointment_ids:
            counts['REFERRED'] += 1
        else:
            counts[apt_status] += 1

    labels = {**APPOINTMENT_STATUS_LABELS, 'REFERRED': 'Referred'}
    return [{"outcome": labels.get(key, key), "count": count} for key, count in counts.most_common()]


def _tally_by_sex_age(qs):
    today = date.today()
    male = female = under_5 = above_5 = total = 0
    for sex, dob in qs.values_list('patient__patient_profile__sex', 'patient__patient_profile__date_of_birth'):
        total += 1
        if sex == 'M':
            male += 1
        elif sex == 'F':
            female += 1

        if dob:
            age_years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        else:
            age_years = None
        if age_years is not None and age_years < 5:
            under_5 += 1
        else:
            above_5 += 1

    return {"male": male, "female": female, "under_5": under_5, "above_5": above_5, "total": total}


def _disease_morbidity_rows(doctor, start_date, end_date):
    base_qs = Consultation.objects.filter(doctor=doctor, created_at__date__range=[start_date, end_date])

    rows = []
    matched_ids = set()
    for label, patterns in DISEASE_MORBIDITY_LIST:
        qs = base_qs.filter(_diagnosis_match_q(patterns))
        matched_ids |= set(qs.values_list('id', flat=True))
        rows.append({"disease": label, **_tally_by_sex_age(qs)})

    others_qs = base_qs.exclude(id__in=matched_ids)
    rows.append({"disease": "Others", **_tally_by_sex_age(others_qs)})
    return rows


@extend_schema(
    tags=["Doctor Reports"],
    summary="Consultation Report",
    description="Total consultations, diagnosis distribution, treatment provided, referral status, and consultation outcome, for the caller's own consultations.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=ConsultationReportResponseSerializer,
)
class ConsultationReportView(APIView):
    permission_classes = [IsDoctor]

    def get(self, request):
        doctor = request.user
        start_date, end_date = get_validated_date_range(request)
        total = Consultation.objects.filter(doctor=doctor, created_at__date__range=[start_date, end_date]).count()

        return Response({
            "start_date": start_date,
            "end_date": end_date,
            "total_consultations": total,
            "diagnosis_distribution": _doctor_diagnosis_distribution(doctor, start_date, end_date),
            "treatment_provided": _doctor_treatment_distribution(doctor, start_date, end_date),
            "referral_status": _doctor_referral_status_distribution(doctor, start_date, end_date),
            "consultation_outcome": _doctor_consultation_outcome_distribution(doctor, start_date, end_date),
        })


@extend_schema(
    tags=["Doctor Reports"],
    summary="Disease Morbidity Report",
    description="Case counts by Male/Female/Under 5/5 Years & Above/Total for a fixed list of diseases (Malaria, ARI, Diarrhoea, Hypertension, Diabetes, Asthma, HIV, TB, Mental Health), plus an Others row for everything else, for the caller's own consultations.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=DiseaseMorbidityReportResponseSerializer,
)
class DiseaseMorbidityReportView(APIView):
    permission_classes = [IsDoctor]

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)
        return Response({
            "start_date": start_date,
            "end_date": end_date,
            "results": _disease_morbidity_rows(request.user, start_date, end_date),
        })


@extend_schema(
    tags=["Doctor Reports"],
    summary="Referral Report",
    description="Paginated list of referrals initiated by the caller: patient, referral date, reason, receiving facility, status, and urgency (Emergency/Routine).",
    parameters=DATE_RANGE_PARAMETERS,
)
class DoctorReferralReportView(generics.GenericAPIView):
    permission_classes = [IsDoctor]
    pagination_class = StandardResultsSetPagination
    serializer_class = DoctorReferralRowSerializer

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)
        qs = Referral.objects.filter(
            referred_by=request.user, created_at__date__range=[start_date, end_date]
        ).select_related('patient', 'receiving_facility').order_by('-created_at')

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = self.get_serializer(page if page is not None else qs, many=True)
        response = paginator.get_paginated_response(serializer.data)
        response.data['start_date'] = start_date
        response.data['end_date'] = end_date
        return response


@extend_schema(
    tags=["Doctor Reports"],
    summary="Adverse Events Report",
    description="Paginated list of adverse events reported by the caller: patient, encounter date, medicine/treatment, adverse event, severity, action taken, reported by, and status.",
    parameters=DATE_RANGE_PARAMETERS,
)
class DoctorAdverseEventsReportView(generics.GenericAPIView):
    permission_classes = [IsDoctor]
    pagination_class = StandardResultsSetPagination
    serializer_class = DoctorAdverseEventRowSerializer

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)
        qs = AdverseEvent.objects.filter(
            reported_by=request.user, date_of_reaction__range=[start_date, end_date]
        ).select_related('patient', 'reported_by', 'suspected_drug').order_by('-date_of_reaction')

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = self.get_serializer(page if page is not None else qs, many=True)
        response = paginator.get_paginated_response(serializer.data)
        response.data['start_date'] = start_date
        response.data['end_date'] = end_date
        return response


@extend_schema(
    tags=["Doctor Reports"],
    summary="Clinical Outcome Report",
    description="Recovered, Admitted, Transferred, Referred, and Deaths for the caller's own patients. Only Referred has a backing model today - the rest are static placeholders until a general clinical-outcome model exists.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=ClinicalOutcomeReportResponseSerializer,
)
class ClinicalOutcomeReportView(APIView):
    permission_classes = [IsDoctor]

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)
        referred = Referral.objects.filter(referred_by=request.user, created_at__date__range=[start_date, end_date]).count()

        return Response({
            "start_date": start_date,
            "end_date": end_date,
            # PLACEHOLDER: no general clinical recovery/discharge model exists yet.
            "recovered": 0,
            # PLACEHOLDER: PatientProfile.birth_status=ADMITTED only tracks newborns.
            "admitted": 0,
            # PLACEHOLDER: no facility-transfer tracking model exists yet.
            "transferred": 0,
            "referred": referred,
            # PLACEHOLDER: no general mortality register exists yet (birth_status=DEAD is neonatal-only).
            "deaths": 0,
        })
