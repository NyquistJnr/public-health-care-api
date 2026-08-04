# core/view_state_admin_reports.py
"""
State Admin Reports: aggregated, state-wide (tenant-wide) reporting endpoints.

Fields that have no corresponding model yet in the system (maternal/neonatal
mortality register, malnutrition/growth-monitoring, cold chain, tracer-drug
list, financial ledger, facility report-submission tracking) are returned as
clearly-labelled static placeholders so the frontend can build against a
stable shape now. Swap them for real queries once the underlying models
exist - search this file for "PLACEHOLDER" to find every one.
"""
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Sum
from django.db.models.functions import TruncDate
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from adverse_events.models import AdverseEvent
from consultations.models import Consultation
from core.models import PatientProfile, User
from core.pagination import StandardResultsSetPagination
from core.permissions import IsStateAdmin
from core.utils import get_validated_date_range
from facilities.models import Facility
from appointments.models import Appointment
from immunization.models import ImmunizationRecord
from inventory.models import InventoryItem, InventoryTransaction
from maternal_care.models import ANCVisit, MaternalCareEpisode
from referrals.models import Referral

from core.serializers_state_admin_reports import (
    FacilityPerformanceReportResponseSerializer, MaternalHealthReportResponseSerializer,
    ChildHealthReportResponseSerializer, DiseaseSurveillanceRowSerializer,
    DrugLogisticsReportResponseSerializer, HumanResourcesReportResponseSerializer,
    FinancialSummaryReportResponseSerializer, ReferralAnalyticsReportResponseSerializer,
    AdverseEventsRowSerializer,
)

DATE_RANGE_PARAMETERS = [
    OpenApiParameter(name='start_date', description='Start date (YYYY-MM-DD). Defaults to 30 days ago.', required=False, type=str),
    OpenApiParameter(name='end_date', description='End date (YYYY-MM-DD). Defaults to today.', required=False, type=str),
]

SEEN_STATUSES = ['IN_CONSULTATION', 'COMPLETED']
FACILITY_STAFF_ROLES = ['DOCTOR', 'PHARMACIST', 'LAB_TECHNICIAN', 'NURSE', 'CHEW', 'IHO', 'OFFICER_IN_CHARGE', 'FACILITY_IT_ADMIN']
OUTBREAK_CASE_THRESHOLD = 5  # PLACEHOLDER heuristic until product defines real per-disease outbreak thresholds


def _facility_qs():
    return Facility.objects.filter(is_active=True).order_by('name')


def _count_by_facility(queryset, facility_field):
    """Runs one grouped Count query and returns {facility_id: count}."""
    rows = queryset.values(facility_field).annotate(c=Count('id')).values_list(facility_field, 'c')
    return dict(rows)


@extend_schema(
    tags=["State Admin Reports"],
    summary="State Facility Performance Report",
    description="Per-facility performance table: patients seen, reports submitted, reporting timeliness, referral rate, and a composite performance score.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=FacilityPerformanceReportResponseSerializer,
)
class FacilityPerformanceReportView(APIView):
    permission_classes = [IsStateAdmin]

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)

        seen_counts = _count_by_facility(
            Appointment.objects.filter(appointment_date__range=[start_date, end_date], status__in=SEEN_STATUSES),
            'facility'
        )
        referral_counts = _count_by_facility(
            Referral.objects.filter(created_at__date__range=[start_date, end_date]),
            'referring_facility'
        )

        results = []
        for f in _facility_qs():
            patients_seen = seen_counts.get(f.id, 0)
            referrals_sent = referral_counts.get(f.id, 0)
            referral_rate = round((referrals_sent / patients_seen * 100), 2) if patients_seen else 0.0

            # PLACEHOLDER: no facility report-submission tracking model exists yet.
            reports_submitted = 0
            reporting_timeliness = 100.0

            performance_score = round(min(patients_seen, 100) * 0.6 + reporting_timeliness * 0.4, 2)

            results.append({
                "facility_id": f.id,
                "facility": f.name,
                "facility_code": f.code,
                "lga": f.lga,
                "patients_seen": patients_seen,
                "reports_submitted": reports_submitted,
                "reporting_timeliness": reporting_timeliness,
                "referral_rate": referral_rate,
                "performance_score": performance_score,
            })

        results.sort(key=lambda r: r['performance_score'], reverse=True)
        return Response({"start_date": start_date, "end_date": end_date, "results": results})


@extend_schema(
    tags=["State Admin Reports"],
    summary="Maternal Health Report",
    description="Per-facility ANC1/ANC4 attendance, deliveries, maternal/neonatal deaths, and IPTp coverage, plus a state comparison chart.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=MaternalHealthReportResponseSerializer,
)
class MaternalHealthReportView(APIView):
    permission_classes = [IsStateAdmin]

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)

        anc_qs = ANCVisit.objects.filter(created_at__date__range=[start_date, end_date])
        anc1_counts = _count_by_facility(anc_qs.filter(visit_sequence_number=1), 'episode__patient__facility')
        anc4_counts = dict(
            anc_qs.filter(visit_sequence_number__gte=4)
            .values('episode__patient__facility')
            .annotate(c=Count('episode', distinct=True))
            .values_list('episode__patient__facility', 'c')
        )
        anc_total_counts = _count_by_facility(anc_qs, 'episode__patient__facility')
        iptp_counts = _count_by_facility(
            anc_qs.exclude(iptp_dose_given__isnull=True).exclude(iptp_dose_given=''),
            'episode__patient__facility'
        )

        delivery_counts = _count_by_facility(
            MaternalCareEpisode.objects.filter(status='DELIVERED', updated_at__date__range=[start_date, end_date]),
            'patient__facility'
        )
        neonatal_death_counts = _count_by_facility(
            PatientProfile.objects.filter(birth_episode__isnull=False, birth_status='DEAD', created_at__date__range=[start_date, end_date]),
            'user__facility'
        )

        results = []
        for f in _facility_qs():
            anc1 = anc1_counts.get(f.id, 0)
            anc4 = anc4_counts.get(f.id, 0)
            anc_total = anc_total_counts.get(f.id, 0)
            iptp_given = iptp_counts.get(f.id, 0)

            results.append({
                "facility_id": f.id,
                "facility": f.name,
                "lga": f.lga,
                "anc_1": anc1,
                "anc_4": anc4,
                "deliveries": delivery_counts.get(f.id, 0),
                # PLACEHOLDER: no maternal mortality register exists yet.
                "maternal_deaths": 0,
                "neonatal_deaths": neonatal_death_counts.get(f.id, 0),
                "iptp_coverage": round((iptp_given / anc_total * 100), 2) if anc_total else 0.0,
            })

        state_comparison_chart = [
            {"facility": r["facility"], "anc_1": r["anc_1"], "anc_4": r["anc_4"], "iptp_coverage": r["iptp_coverage"]}
            for r in results
        ]

        return Response({
            "start_date": start_date,
            "end_date": end_date,
            "results": results,
            "state_comparison_chart": state_comparison_chart,
        })


@extend_schema(
    tags=["State Admin Reports"],
    summary="Child Health Report",
    description="Per-facility immunization counts (BCG, Penta 1, Penta 3, Measles), SAM cases, and growth monitoring.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=ChildHealthReportResponseSerializer,
)
class ChildHealthReportView(APIView):
    permission_classes = [IsStateAdmin]

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)

        imm_qs = ImmunizationRecord.objects.filter(date_of_visit__range=[start_date, end_date])
        bcg_counts = _count_by_facility(imm_qs.filter(vaccine_given__name__icontains='BCG'), 'facility')
        penta1_counts = _count_by_facility(imm_qs.filter(vaccine_given__name__icontains='Penta', dose_number=1), 'facility')
        penta3_counts = _count_by_facility(imm_qs.filter(vaccine_given__name__icontains='Penta', dose_number=3), 'facility')
        measles_counts = _count_by_facility(imm_qs.filter(vaccine_given__name__icontains='Measles'), 'facility')

        results = []
        for f in _facility_qs():
            results.append({
                "facility_id": f.id,
                "facility": f.name,
                "lga": f.lga,
                "bcg": bcg_counts.get(f.id, 0),
                "penta_1": penta1_counts.get(f.id, 0),
                "penta_3": penta3_counts.get(f.id, 0),
                "measles": measles_counts.get(f.id, 0),
                # PLACEHOLDER: no malnutrition/SAM or growth-monitoring model exists yet.
                "sam_cases": 0,
                "growth_monitoring": 0,
            })

        return Response({"start_date": start_date, "end_date": end_date, "results": results})


@extend_schema(
    tags=["State Admin Reports"],
    summary="Disease Surveillance Report",
    description="Paginated disease x facility case table with trend direction and alert level, plus a state trend chart, LGA heat map, and outbreak indicators.",
    parameters=DATE_RANGE_PARAMETERS,
)
class DiseaseSurveillanceReportView(generics.GenericAPIView):
    permission_classes = [IsStateAdmin]
    pagination_class = StandardResultsSetPagination
    serializer_class = DiseaseSurveillanceRowSerializer

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)
        base_qs = Consultation.objects.filter(created_at__date__range=[start_date, end_date], diagnosed_disease__isnull=False)

        grouped = (
            base_qs.values(
                'diagnosed_disease__id', 'diagnosed_disease__name', 'diagnosed_disease__severity',
                'appointment__facility__id', 'appointment__facility__name', 'appointment__facility__lga'
            )
            .annotate(cases=Count('id'))
            .order_by('-cases')
        )

        midpoint = start_date + (end_date - start_date) / 2

        # Build (disease_id, facility_id) -> count maps for the two halves of the range.
        def _half_counts(qs):
            rows = qs.values('diagnosed_disease__id', 'appointment__facility__id').annotate(c=Count('id'))
            return {(row['diagnosed_disease__id'], row['appointment__facility__id']): row['c'] for row in rows}

        first_half = _half_counts(base_qs.filter(created_at__date__lt=midpoint))
        second_half = _half_counts(base_qs.filter(created_at__date__gte=midpoint))

        table_rows = []
        for row in grouped:
            key = (row['diagnosed_disease__id'], row['appointment__facility__id'])
            before, after = first_half.get(key, 0), second_half.get(key, 0)
            if after > before:
                trend = 'INCREASING'
            elif after < before:
                trend = 'DECREASING'
            else:
                trend = 'STABLE'

            table_rows.append({
                "disease": row['diagnosed_disease__name'],
                "cases": row['cases'],
                "lga": row['appointment__facility__lga'],
                "facility": row['appointment__facility__name'],
                "trend": trend,
                "alert_level": row['diagnosed_disease__severity'],
            })

        trend_rows = (
            base_qs.annotate(date=TruncDate('created_at')).values('date').annotate(cases=Count('id')).order_by('date')
        )
        state_trend_chart = [{"date": row['date'], "cases": row['cases']} for row in trend_rows]

        lga_heatmap = [
            {"lga": row['appointment__facility__lga'], "cases": row['cases']}
            for row in base_qs.values('appointment__facility__lga').annotate(cases=Count('id')).order_by('-cases')
        ]

        outbreak_indicators = [
            {
                "disease": row['diagnosed_disease__name'],
                "cases": row['cases'],
                "alert_level": row['diagnosed_disease__severity'],
                "facilities_affected": row['facilities_affected'],
            }
            for row in base_qs.values('diagnosed_disease__name', 'diagnosed_disease__severity')
            .annotate(cases=Count('id'), facilities_affected=Count('appointment__facility', distinct=True))
            .filter(cases__gte=OUTBREAK_CASE_THRESHOLD)
            .order_by('-cases')
        ]

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(table_rows, request, view=self)
        response = paginator.get_paginated_response(page if page is not None else table_rows)
        response.data['start_date'] = start_date
        response.data['end_date'] = end_date
        response.data['state_trend_chart'] = state_trend_chart
        response.data['lga_heatmap'] = lga_heatmap
        response.data['outbreak_indicators'] = outbreak_indicators
        return response


@extend_schema(
    tags=["State Admin Reports"],
    summary="Drug Logistics Report",
    description="Per-facility stock-outs, vaccine wastage, cold chain status, and tracer drug availability.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=DrugLogisticsReportResponseSerializer,
)
class DrugLogisticsReportView(APIView):
    permission_classes = [IsStateAdmin]

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)

        # Fetch raw per-item stock totals, then tally per facility in Python -
        # chaining two dependent aggregates (Sum then Count) in one queryset
        # would double-count rows, so we deliberately don't do that here.
        drug_items = (
            InventoryItem.objects.filter(inventory_category='DRUG', is_active=True)
            .annotate(total_remaining=Sum('batches__remaining_quantity'))
            .values('facility', 'total_remaining')
        )
        stockouts_by_facility, drug_item_count_by_facility, in_stock_by_facility = {}, {}, {}
        for item in drug_items:
            fid = item['facility']
            remaining = item['total_remaining'] or 0
            drug_item_count_by_facility[fid] = drug_item_count_by_facility.get(fid, 0) + 1
            if remaining <= 0:
                stockouts_by_facility[fid] = stockouts_by_facility.get(fid, 0) + 1
            else:
                in_stock_by_facility[fid] = in_stock_by_facility.get(fid, 0) + 1

        immunization_batches = (
            InventoryItem.objects.filter(drug_classification='IMMUNIZATION', is_active=True)
            .values('facility')
            .annotate(issued=Sum('batches__initial_quantity'))
        )
        issued_by_facility = {row['facility']: (row['issued'] or 0) for row in immunization_batches}

        expired_qty = (
            InventoryTransaction.objects.filter(
                transaction_type='EXPIRED',
                batch__item__drug_classification='IMMUNIZATION',
                created_at__date__range=[start_date, end_date],
            )
            .values('batch__item__facility')
            .annotate(qty=Sum('quantity'))
        )
        expired_by_facility = {row['batch__item__facility']: abs(row['qty'] or 0) for row in expired_qty}

        results = []
        for f in _facility_qs():
            issued = issued_by_facility.get(f.id, 0)
            expired = expired_by_facility.get(f.id, 0)
            total_drug_items = drug_item_count_by_facility.get(f.id, 0)
            in_stock_items = in_stock_by_facility.get(f.id, 0)

            results.append({
                "facility_id": f.id,
                "facility": f.name,
                "lga": f.lga,
                "stock_outs": stockouts_by_facility.get(f.id, 0),
                "vaccine_wastage": round((expired / issued * 100), 2) if issued else 0.0,
                # PLACEHOLDER: no cold chain monitoring model exists yet.
                "cold_chain_status": "NOT_TRACKED",
                # Approximated as % of DRUG-category items currently in stock; no dedicated
                # tracer-drug list model exists yet, so this covers all drugs, not a curated tracer list.
                "tracer_drug_availability": round((in_stock_items / total_drug_items * 100), 2) if total_drug_items else 0.0,
            })

        return Response({"start_date": start_date, "end_date": end_date, "results": results})


@extend_schema(
    tags=["State Admin Reports"],
    summary="Human Resources Report",
    description="Per-facility staff headcount by role and an activity-based attendance percentage.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=HumanResourcesReportResponseSerializer,
)
class HumanResourcesReportView(APIView):
    permission_classes = [IsStateAdmin]

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)

        nurse_counts = _count_by_facility(User.objects.filter(role='NURSE', is_active=True), 'facility')
        chew_counts = _count_by_facility(User.objects.filter(role='CHEW', is_active=True), 'facility')
        doctor_counts = _count_by_facility(User.objects.filter(role='DOCTOR', is_active=True), 'facility')

        staff_qs = User.objects.filter(role__in=FACILITY_STAFF_ROLES, is_active=True)
        total_staff_counts = _count_by_facility(staff_qs, 'facility')
        # Proxy for attendance: staff who made at least one authenticated request in the period.
        present_staff_counts = _count_by_facility(staff_qs.filter(last_active__date__range=[start_date, end_date]), 'facility')

        results = []
        for f in _facility_qs():
            total_staff = total_staff_counts.get(f.id, 0)
            present_staff = present_staff_counts.get(f.id, 0)

            results.append({
                "facility_id": f.id,
                "facility": f.name,
                "lga": f.lga,
                "nurses": nurse_counts.get(f.id, 0),
                # PLACEHOLDER: 'Community Health Officer' is not a distinct role in the system yet (see User.ROLE_CHOICES).
                "chos": 0,
                "chews": chew_counts.get(f.id, 0),
                "doctors": doctor_counts.get(f.id, 0),
                # Approximated from login activity in the period, not biometric/manual attendance.
                "attendance_percent": round((present_staff / total_staff * 100), 2) if total_staff else 0.0,
            })

        return Response({"start_date": start_date, "end_date": end_date, "results": results})


@extend_schema(
    tags=["State Admin Reports"],
    summary="Financial Summary Report",
    description="Per-facility revenue, expenditure, BHCPF funds, and balance. No financial/ledger model exists yet, so all figures are static placeholders pending finance module design.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=FinancialSummaryReportResponseSerializer,
)
class FinancialSummaryReportView(APIView):
    permission_classes = [IsStateAdmin]

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)

        # PLACEHOLDER: no financial/ledger model exists anywhere in the system yet.
        results = [
            {
                "facility_id": f.id,
                "facility": f.name,
                "lga": f.lga,
                "revenue": 0.0,
                "expenditure": 0.0,
                "bhcpf_funds": 0.0,
                "balance": 0.0,
            }
            for f in _facility_qs()
        ]

        return Response({"start_date": start_date, "end_date": end_date, "results": results})


@extend_schema(
    tags=["State Admin Reports"],
    summary="Referral Analytics Report",
    description="Per-facility referrals sent/received, ambulance referrals, completion rate, and average referral time (for completed referrals).",
    parameters=DATE_RANGE_PARAMETERS,
    responses=ReferralAnalyticsReportResponseSerializer,
)
class ReferralAnalyticsReportView(APIView):
    permission_classes = [IsStateAdmin]

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)

        sent_qs = Referral.objects.filter(created_at__date__range=[start_date, end_date])
        sent_counts = _count_by_facility(sent_qs, 'referring_facility')
        received_counts = _count_by_facility(sent_qs.filter(receiving_facility__isnull=False), 'receiving_facility')
        ambulance_counts = _count_by_facility(sent_qs.filter(mode_of_transportation='AMBULANCE'), 'referring_facility')
        completed_counts = _count_by_facility(sent_qs.filter(status='COMPLETED'), 'referring_facility')

        avg_duration_rows = (
            sent_qs.filter(status='COMPLETED')
            .annotate(duration=ExpressionWrapper(F('updated_at') - F('created_at'), output_field=DurationField()))
            .values('referring_facility')
            .annotate(avg_duration=Avg('duration'))
        )
        avg_hours_by_facility = {
            row['referring_facility']: round(row['avg_duration'].total_seconds() / 3600, 2)
            for row in avg_duration_rows if row['avg_duration'] is not None
        }

        results = []
        for f in _facility_qs():
            sent = sent_counts.get(f.id, 0)
            completed = completed_counts.get(f.id, 0)

            results.append({
                "facility_id": f.id,
                "facility": f.name,
                "lga": f.lga,
                "referrals_sent": sent,
                "referrals_received": received_counts.get(f.id, 0),
                "ambulance_referrals": ambulance_counts.get(f.id, 0),
                "completion_rate": round((completed / sent * 100), 2) if sent else 0.0,
                "average_referral_time_hours": avg_hours_by_facility.get(f.id, 0.0),
            })

        return Response({"start_date": start_date, "end_date": end_date, "results": results})


@extend_schema(
    tags=["State Admin Reports"],
    summary="Adverse Events Report",
    description="Paginated adverse drug event log with summary cards (total, severe, resolved, pending, most common drug/reaction). Facility is derived from the reporting staff member's facility.",
    parameters=DATE_RANGE_PARAMETERS,
)
class AdverseEventsReportView(generics.GenericAPIView):
    permission_classes = [IsStateAdmin]
    pagination_class = StandardResultsSetPagination
    serializer_class = AdverseEventsRowSerializer

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)
        qs = AdverseEvent.objects.filter(created_at__date__range=[start_date, end_date]).select_related(
            'patient', 'reported_by', 'reported_by__facility', 'suspected_drug'
        ).order_by('-created_at')

        total = qs.count()
        severe = qs.filter(severity__in=['SEVERE', 'LIFE_THREATENING', 'FATAL']).count()
        resolved = qs.filter(status__in=['RESOLVED', 'CLOSED']).count()
        pending = qs.filter(status__in=['REPORTED', 'UNDER_REVIEW']).count()

        top_drug_row = qs.values('suspected_drug__name').annotate(c=Count('id')).order_by('-c').first()
        top_reaction_row = qs.values('reaction_type').annotate(c=Count('id')).order_by('-c').first()

        def _serialize(e):
            return {
                "event_id": e.event_id,
                "facility": e.reported_by.facility.name if e.reported_by and e.reported_by.facility else None,
                "patient": f"{e.patient.first_name} {e.patient.last_name}",
                "drug_treatment": e.suspected_drug.name,
                "adverse_event": e.reaction_type,
                "severity": e.severity,
                "status": e.status,
                "date_reported": e.created_at.date(),
            }

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        table_rows = [_serialize(e) for e in (page if page is not None else qs)]
        response = paginator.get_paginated_response(table_rows)
        response.data['start_date'] = start_date
        response.data['end_date'] = end_date
        response.data['summary_cards'] = {
            "total_adverse_events": total,
            "severe_events": severe,
            "resolved": resolved,
            "pending": pending,
            "most_common_drug": top_drug_row['suspected_drug__name'] if top_drug_row else None,
            "most_common_reaction": top_reaction_row['reaction_type'] if top_reaction_row else None,
        }
        return response
