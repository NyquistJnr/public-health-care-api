# nurse_chew/views.py
from datetime import timedelta
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from appointments.models import Appointment
from maternal_care.models import ANCVisit
from core.models import PatientProfile
from .serializers import NurseStatsResponseSerializer
from rest_framework import generics
from django.db.models import Q
from laboratory.models import LabRequest
from prescriptions.models import Prescription
from referrals.models import Referral
from appointments.serializers import AppointmentReadSerializer
from laboratory.serializers import LabRequestReadSerializer
from prescriptions.serializers import PrescriptionReadSerializer
from referrals.serializers import ReferralReadSerializer

@extend_schema(
    tags=["Nurse/CHEW Dashboard"],
    summary="Get Nurse Daily Queue & Preventative Stats",
    parameters=[
        OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
    ]
)
class NurseDashboardStatsView(APIView):
    serializer_class = NurseStatsResponseSerializer

    def get(self, request):
        facility = request.user.facility
        now = timezone.now()
        
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        appt_qs = Appointment.objects.filter(facility=facility)
        anc_qs = ANCVisit.objects.filter(appointment__facility=facility, episode__status='ACTIVE')

        if start_date:
            appt_qs = appt_qs.filter(appointment_date__gte=start_date)
            anc_qs = anc_qs.filter(created_at__gte=start_date)
        if end_date:
            appt_qs = appt_qs.filter(appointment_date__lte=end_date)
            anc_qs = anc_qs.filter(created_at__lte=end_date)

        waiting_in_queue = appt_qs.filter(status__in=['SCHEDULED', 'ARRIVED']).count()
        vitals_pending = appt_qs.filter(status='ARRIVED').count()
        maternal_alerts = anc_qs.exclude(risk_factors__isnull=True).exclude(risk_factors__exact='').count()
        twenty_eight_days_ago = now.date() - timedelta(days=28)
        
        vaccines_due = PatientProfile.objects.filter(
            user__facility=facility,
            date_of_birth__gte=twenty_eight_days_ago,
            user__immunizations__isnull=True
        ).count()

        return Response({
            "waiting_in_queue": waiting_in_queue,
            "vitals_pending": vitals_pending,
            "maternal_alerts": maternal_alerts,
            "vaccines_due": vaccines_due
        })

@extend_schema(
    tags=["Patient Management"],
    summary="Get Patient's Appointment History",
    parameters=[
        OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='staff_id', description='Filter by Assigned Staff UUID', required=False, type=str),
    ]
)
class PatientAppointmentsView(generics.ListAPIView):
    serializer_class = AppointmentReadSerializer

    def get_queryset(self):
        patient_id = self.kwargs.get('patient_id')
        qs = Appointment.objects.filter(patient_id=patient_id, facility=self.request.user.facility)
        
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        staff_id = self.request.query_params.get('staff_id')

        if start_date: qs = qs.filter(appointment_date__gte=start_date)
        if end_date: qs = qs.filter(appointment_date__lte=end_date)
        if staff_id: qs = qs.filter(assigned_to__id=staff_id)

        return qs.order_by('-appointment_date', '-appointment_time')


@extend_schema(
    tags=["Patient Management"],
    summary="Get Patient's Lab Requests",
    parameters=[
        OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='status', description='PENDING, PARTIAL, COMPLETED', required=False, type=str),
        OpenApiParameter(name='search', description='Search by specific Test Name', required=False, type=str),
    ]
)
class PatientLabRequestsView(generics.ListAPIView):
    serializer_class = LabRequestReadSerializer

    def get_queryset(self):
        patient_id = self.kwargs.get('patient_id')
        qs = LabRequest.objects.filter(patient_id=patient_id, patient__facility=self.request.user.facility)
        
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        status = self.request.query_params.get('status')
        search = self.request.query_params.get('search')

        if start_date: qs = qs.filter(created_at__gte=start_date)
        if end_date: qs = qs.filter(created_at__lte=end_date)
        if status: qs = qs.filter(status=status.upper())
        if search:
            qs = qs.filter(tests__test_name__icontains=search).distinct()

        return qs.order_by('-created_at')


@extend_schema(
    tags=["Patient Management"],
    summary="Get Patient's Prescriptions",
    parameters=[
        OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='status', description='PENDING, PARTIAL, DISPENSED', required=False, type=str),
        OpenApiParameter(name='search', description='Search by Medication Name', required=False, type=str),
    ]
)
class PatientPrescriptionsView(generics.ListAPIView):
    serializer_class = PrescriptionReadSerializer

    def get_queryset(self):
        patient_id = self.kwargs.get('patient_id')
        qs = Prescription.objects.filter(patient_id=patient_id, patient__facility=self.request.user.facility)
        
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        status = self.request.query_params.get('status')
        search = self.request.query_params.get('search')

        if start_date: qs = qs.filter(created_at__gte=start_date)
        if end_date: qs = qs.filter(created_at__lte=end_date)
        if status: qs = qs.filter(status=status.upper())
        if search:
            qs = qs.filter(
                Q(items__drug__name__icontains=search) |
                Q(items__custom_drug_name__icontains=search)
            ).distinct()

        return qs.order_by('-created_at')


@extend_schema(
    tags=["Patient Management"],
    summary="Get Patient's Referral History",
    parameters=[
        OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='status', description='PENDING, ACCEPTED, REJECTED', required=False, type=str),
        OpenApiParameter(name='direction', description='outbound (Sent away) or inbound (Received). Default is all.', required=False, type=str),
    ]
)
class PatientReferralsView(generics.ListAPIView):
    serializer_class = ReferralReadSerializer

    def get_queryset(self):
        patient_id = self.kwargs.get('patient_id')
        facility = self.request.user.facility
        qs = Referral.objects.filter(
            Q(patient_id=patient_id) &
            (Q(referring_facility=facility) | Q(receiving_facility=facility))
        )
        
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        status = self.request.query_params.get('status')
        direction = self.request.query_params.get('direction')

        if start_date: qs = qs.filter(created_at__gte=start_date)
        if end_date: qs = qs.filter(created_at__lte=end_date)
        if status: qs = qs.filter(status=status.upper())
        
        if direction:
            if direction.lower() == 'outbound':
                qs = qs.filter(referring_facility=facility)
            elif direction.lower() == 'inbound':
                qs = qs.filter(receiving_facility=facility)

        return qs.order_by('-created_at').distinct()
