# doctors/views.py
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter

from appointments.models import Appointment
from laboratory.models import LabRequest, LabTest
from maternal_care.models import ANCVisit
from core.models import PatientProfile
from referrals.models import Referral
from laboratory.serializers import LabRequestReadSerializer
from .serializers import DoctorStatsResponseSerializer, DoctorAlertsResponseSerializer

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


@extend_schema(tags=["Doctor Dashboard"], summary="Get Doctor Actionable Alerts")
class DoctorAlertsView(APIView):
    serializer_class = DoctorAlertsResponseSerializer

    def get(self, request):
        user = request.user
        facility = user.facility
        now = timezone.now()
        yesterday = now - timedelta(days=1)

        response_data = {}

        high_risk_pregnancies = ANCVisit.objects.filter(
            created_by=user,
            episode__status='ACTIVE'
        ).exclude(risk_factors__isnull=True).exclude(risk_factors__exact='').count()

        if high_risk_pregnancies > 0:
            response_data['pregnancy'] = {
                "high_risk_count": high_risk_pregnancies
            }

        twenty_eight_days_ago = now.date() - timedelta(days=28)
        due_neonates = PatientProfile.objects.filter(
            user__facility=facility,
            date_of_birth__gte=twenty_eight_days_ago,
            user__immunizations__isnull=True
        ).count()

        if due_neonates > 0:
            response_data['immunization'] = {
                "due_for_immunization": due_neonates
            }

        pending_referrals = Referral.objects.filter(referred_by=user, status='PENDING').order_by('-created_at')
        pending_ref_count = pending_referrals.count()
        
        if pending_ref_count > 0:
            top_referrals = pending_referrals[:5]
            response_data['referrals'] = {
                "total_pending": pending_ref_count,
                "recent_pending": [
                    {
                        "referral_id": ref.referral_id,
                        "patient_name": ref.patient.get_full_name(),
                        "target_facility": ref.receiving_facility.name,
                        "date": ref.created_at
                    } for ref in top_referrals
                ]
            }

        ready_tests = LabTest.objects.filter(
            lab_request__requested_by=user, 
            test_status='RESULT_READY', 
            result_date__gte=yesterday
        ).order_by('-result_date')

        pending_requests = LabRequest.objects.filter(
            requested_by=user, 
            status__in=['PENDING', 'PARTIAL']
        ).order_by('-created_at')

        ready_count = ready_tests.count()
        pending_lab_count = pending_requests.count()

        if ready_count > 0 or pending_lab_count > 0:
            response_data['labs'] = {
                "ready_24h_count": ready_count,
                "pending_count": pending_lab_count,
                "recent_ready_tests": [
                    {
                        "test_name": test.test_name,
                        "patient_name": test.lab_request.patient.get_full_name(),
                        "result_date": test.result_date
                    } for test in ready_tests[:5]
                ],
                "recent_pending_requests": [
                    {
                        "request_id": req.request_id,
                        "patient_name": req.patient.get_full_name(),
                        "date_ordered": req.created_at
                    } for req in pending_requests[:5]
                ]
            }

        return Response(response_data)

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
