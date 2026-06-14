# doctors/views.py
from datetime import datetime, date
from django.utils import timezone
from django.db.models import Q
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from appointments.models import Appointment
from laboratory.models import LabRequest, LabTest
from maternal_care.models import ANCVisit, PNCVisit
from immunization.models import ImmunizationRecord
from core.models import PatientProfile
from referrals.models import Referral
from laboratory.serializers import LabRequestReadSerializer
from core.pagination import StandardResultsSetPagination

from .serializers import (
    DoctorStatsResponseSerializer, 
    PaginatedDoctorAlertsResponseSerializer
)

@extend_schema(
    tags=["Doctor Dashboard"],
    summary="Get Doctor Daily Statistics",
    parameters=[
        OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
    ]
)
class DoctorStatsView(APIView):
    serializer_class = DoctorStatsResponseSerializer

    def get(self, request):
        user = request.user
        
        appt_qs = Appointment.objects.filter(assigned_to=user)
        lab_qs = LabRequest.objects.filter(requested_by=user)

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if start_date:
            appt_qs = appt_qs.filter(appointment_date__gte=start_date)
            lab_qs = lab_qs.filter(created_at__gte=start_date)
        if end_date:
            appt_qs = appt_qs.filter(appointment_date__lte=end_date)
            lab_qs = lab_qs.filter(created_at__lte=end_date)

        return Response({
            "waiting": appt_qs.filter(status__in=['ARRIVED', 'VITALS_DONE']).count(),
            "in_consultation": appt_qs.filter(status='IN_CONSULTATION').count(),
            "completed": appt_qs.filter(status='COMPLETED').count(),
            "pending_labs": lab_qs.filter(status__in=['PENDING', 'PARTIAL']).count(),
        })


@extend_schema(tags=["Doctor Dashboard"], summary="Get All Pending Lab Requests for Doctor")
class DoctorPendingLabsView(generics.ListAPIView):
    serializer_class = LabRequestReadSerializer
    
    def get_queryset(self):
        return LabRequest.objects.filter(
            requested_by=self.request.user,
            status__in=['PENDING', 'PARTIAL']
        ).order_by('-created_at')


@extend_schema(
    tags=["Doctor Dashboard"], 
    summary="Get Unified Doctor Actionable Timeline",
    parameters=[
        OpenApiParameter(name='alert_type', description='Comma-separated list (e.g., ANC, LAB, REFERRAL, IMMUNIZATION)', required=False, type=str),
        OpenApiParameter(name='page', description='Page number', required=False, type=int),
        OpenApiParameter(name='page_size', description='Items per page', required=False, type=int),
    ]
)
class DoctorAlertsView(APIView):
    serializer_class = PaginatedDoctorAlertsResponseSerializer

    def get(self, request):
        user = request.user
        now = timezone.now()
        today = now.date()
        alerts = []

        alert_type_param = request.query_params.get('alert_type')
        if alert_type_param:
            allowed_types = [t.strip().upper() for t in alert_type_param.split(',')]
        else:
            allowed_types = ['ANC', 'PNC', 'IMMUNIZATION', 'REFERRAL', 'LAB']

        if 'ANC' in allowed_types:
            anc_visits = ANCVisit.objects.filter(
                episode__status='ACTIVE',
                next_visit_date__isnull=False,
                appointment__assigned_to=user 
            ).select_related('episode__patient__patient_profile')

            for anc in anc_visits:
                alerts.append({
                    "alert_type": "ANC",
                    "patient_name": anc.episode.patient.get_full_name(),
                    "patient_id": anc.episode.patient.patient_profile.patient_id,
                    "date": anc.next_visit_date,
                    "status": "UPCOMING" if anc.next_visit_date >= today else "OVERDUE",
                    "details": f"Sequence {anc.visit_sequence_number + 1} Due"
                })

        if 'PNC' in allowed_types:
            pnc_visits = PNCVisit.objects.filter(
                episode__status__in=['ACTIVE', 'DELIVERED'],
                next_visit_date__isnull=False,
                appointment__assigned_to=user
            ).select_related('episode__patient__patient_profile')

            for pnc in pnc_visits:
                alerts.append({
                    "alert_type": "PNC",
                    "patient_name": pnc.episode.patient.get_full_name(),
                    "patient_id": pnc.episode.patient.patient_profile.patient_id,
                    "date": pnc.next_visit_date,
                    "status": "UPCOMING" if pnc.next_visit_date >= today else "OVERDUE",
                    "details": f"Sequence {pnc.visit_sequence_number + 1} Due"
                })

        if 'IMMUNIZATION' in allowed_types:
            immunizations = ImmunizationRecord.objects.filter(
                next_due_date__isnull=False,
                administered_by=user
            ).select_related('patient__patient_profile', 'vaccine_given')

            for imm in immunizations:
                alerts.append({
                    "alert_type": "IMMUNIZATION",
                    "patient_name": imm.patient.get_full_name(),
                    "patient_id": imm.patient.patient_profile.patient_id,
                    "date": imm.next_due_date,
                    "status": "UPCOMING" if imm.next_due_date >= today else "OVERDUE",
                    "details": f"{imm.vaccine_given.name} Dose {imm.dose_number + 1}"
                })

        if 'REFERRAL' in allowed_types:
            referrals = Referral.objects.filter(referred_by=user).select_related(
                'patient__patient_profile', 'receiving_facility'
            )

            for ref in referrals:
                target_name = ref.receiving_facility.name if ref.receiving_facility else ref.get_destination_level_display()
                alerts.append({
                    "alert_type": "REFERRAL",
                    "patient_name": ref.patient.get_full_name(),
                    "patient_id": ref.patient.patient_profile.patient_id,
                    "date": ref.updated_at,
                    "status": ref.status,
                    "details": f"To: {target_name}"
                })

        if 'LAB' in allowed_types:
            labs = LabTest.objects.filter(
                lab_request__requested_by=user,
                test_status__in=['PENDING', 'PROCESSING', 'RESULT_READY']
            ).select_related('lab_request__patient__patient_profile')

            for lab in labs:
                target_date = lab.result_date if lab.result_date else lab.updated_at
                alerts.append({
                    "alert_type": "LAB",
                    "patient_name": lab.lab_request.patient.get_full_name(),
                    "patient_id": lab.lab_request.patient.patient_profile.patient_id,
                    "date": target_date,
                    "status": lab.test_status,
                    "details": f"Test: {lab.test_name}"
                })

        def get_datetime_diff(item_date):
            if not item_date:
                return float('inf') 
            
            if isinstance(item_date, date) and not isinstance(item_date, datetime):
                item_date = timezone.make_aware(datetime.combine(item_date, datetime.min.time()))
                
            return abs((item_date - now).total_seconds())

        alerts.sort(key=lambda x: get_datetime_diff(x['date']))

        paginator = StandardResultsSetPagination()
        paginated_alerts = paginator.paginate_queryset(alerts, request, view=self)
        
        return paginator.get_paginated_response(paginated_alerts)


@extend_schema(
    tags=["Doctor Dashboard"], 
    summary="Get All Lab Requests Ordered by Logged-in Doctor",
    parameters=[
        OpenApiParameter(name='status', description='PENDING, PARTIAL, COMPLETED, CANCELLED', required=False, type=str),
        OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='search', description='Search by Patient Name, PT-ID, or Lab Request ID', required=False, type=str),
    ]
)
class DoctorAllLabRequestsView(generics.ListAPIView):
    serializer_class = LabRequestReadSerializer
    
    def get_queryset(self):
        qs = LabRequest.objects.filter(requested_by=self.request.user)
        
        req_status = self.request.query_params.get('status')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        search = self.request.query_params.get('search')

        if req_status:
            qs = qs.filter(status=req_status.upper())
        if start_date:
            qs = qs.filter(created_at__gte=start_date)
        if end_date:
            qs = qs.filter(created_at__lte=end_date)
            
        if search:
            qs = qs.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search) |
                Q(patient__patient_profile__patient_id__icontains=search) |
                Q(request_id__icontains=search)
            )

        return qs.order_by('-created_at')
