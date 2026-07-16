# nurse_chew/views.py
from datetime import timedelta
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework import generics, viewsets
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db.models import Q
from core.pagination import StandardResultsSetPagination
from appointments.models import Appointment
from maternal_care.models import ANCVisit, PNCVisit
from core.models import PatientProfile
from immunization.models import ImmunizationRecord
from laboratory.models import LabRequest
from prescriptions.models import Prescription
from referrals.models import Referral
from django.db.models import Count, Q, Value, CharField, F
from django.db.models.functions import Concat, Cast
from core.models import User
from appointments.serializers import AppointmentReadSerializer
from laboratory.serializers import LabRequestReadSerializer
from prescriptions.serializers import PrescriptionReadSerializer
from referrals.serializers import ReferralReadSerializer
from .models import HealthPromotion, PostActivity
from .serializers import (
    NurseStatsResponseSerializer,
    PaginatedMaternalAlertsSerializer,
    ImmunizationDueItemSerializer,
    HealthPromotionSerializer,
    PostActivitySerializer,
    ChewStatsResponseSerializer,
    HealthPromotionTodaySerializer,
    ChewActivityReportStatsSerializer,
    ActivityReportItemSerializer
)

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

@extend_schema(
    tags=["Nurse/CHEW Dashboard"],
    summary="Get Maternal Alerts (Urgent Appointments & Overdue Visits)",
    parameters=[
        OpenApiParameter(name='page', description='Page number', required=False, type=int),
        OpenApiParameter(name='page_size', description='Items per page (Default 10, Max 100)', required=False, type=int),
    ],
    responses=PaginatedMaternalAlertsSerializer
)
class MaternalAlertsView(APIView):
    def get(self, request):
        facility = request.user.facility
        today = timezone.now().date()
        alerts = []

        urgent_appts = Appointment.objects.filter(
            facility=facility,
            status__in=['SCHEDULED', 'ARRIVED', 'VITALS_DONE'],
            priority__in=['URGENT', 'CRITICAL'],
            visit_type__in=['ANTENATAL', 'POSTNATAL']
        ).select_related('patient__patient_profile')

        for appt in urgent_appts:
            alerts.append({
                "alert_type": "URGENT_APPOINTMENT",
                "patient_name": appt.patient.get_full_name(),
                "patient_id": appt.patient.patient_profile.patient_id,
                "date": appt.appointment_date,
                "priority": appt.priority,
                "details": f"{appt.get_visit_type_display()} - {appt.get_status_display()}"
            })

        latest_anc_ids = ANCVisit.objects.filter(
            appointment__facility=facility,
            next_visit_date__isnull=False,
            episode__status='ACTIVE'
        ).order_by('episode', '-created_at').distinct('episode').values_list('id', flat=True)

        due_ancs = ANCVisit.objects.filter(
            id__in=latest_anc_ids,
            next_visit_date__lte=today + timedelta(days=7)
        ).select_related('episode__patient__patient_profile')

        for anc in due_ancs:
            priority = "CRITICAL" if anc.next_visit_date < today else "NORMAL"
            alerts.append({
                "alert_type": "OVERDUE_ANC",
                "patient_name": anc.episode.patient.get_full_name(),
                "patient_id": anc.episode.patient.patient_profile.patient_id,
                "date": anc.next_visit_date,
                "priority": priority,
                "details": f"ANC Sequence {anc.visit_sequence_number + 1} is due."
            })

        latest_pnc_ids = PNCVisit.objects.filter(
            appointment__facility=facility,
            next_visit_date__isnull=False,
            episode__status__in=['ACTIVE', 'DELIVERED']
        ).order_by('episode', '-created_at').distinct('episode').values_list('id', flat=True)

        due_pncs = PNCVisit.objects.filter(
            id__in=latest_pnc_ids,
            next_visit_date__lte=today + timedelta(days=7)
        ).select_related('episode__patient__patient_profile')

        for pnc in due_pncs:
            priority = "CRITICAL" if pnc.next_visit_date < today else "NORMAL"
            alerts.append({
                "alert_type": "OVERDUE_PNC",
                "patient_name": pnc.episode.patient.get_full_name(),
                "patient_id": pnc.episode.patient.patient_profile.patient_id,
                "date": pnc.next_visit_date,
                "priority": priority,
                "details": f"PNC Sequence {pnc.visit_sequence_number + 1} is due."
            })

        def sort_key(item):
            priority_weight = 0 if item['priority'] in ['CRITICAL', 'URGENT'] else 1
            return (item['date'], priority_weight)

        alerts.sort(key=sort_key)

        paginator = StandardResultsSetPagination()
        paginated_alerts = paginator.paginate_queryset(alerts, request, view=self)
        
        return paginator.get_paginated_response(paginated_alerts)

@extend_schema(
    tags=["Nurse/CHEW Dashboard"],
    summary="Get Scheduled and Overdue Immunizations",
    parameters=[
        OpenApiParameter(name='search', description='Search by Patient Name', required=False, type=str),
    ]
)
class ImmunizationsDueView(generics.ListAPIView):
    serializer_class = ImmunizationDueItemSerializer

    def get_queryset(self):
        facility = self.request.user.facility
        
        latest_record_ids = ImmunizationRecord.objects.filter(
            facility=facility,
            next_due_date__isnull=False
        ).order_by(
            'patient', 'vaccine_given', '-date_of_visit'
        ).distinct('patient', 'vaccine_given').values_list('id', flat=True)

        today = timezone.now().date()
        qs = ImmunizationRecord.objects.filter(
            id__in=latest_record_ids,
            next_due_date__lte=today + timedelta(days=30)
        ).select_related('patient__patient_profile', 'vaccine_given')

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search) |
                Q(vaccine_given__name__icontains=search)
            )

        return qs.order_by('next_due_date')

@extend_schema(
    tags=["Health Promotion"],
    parameters=[
        OpenApiParameter(name='search', description='Search by ID, Promotion ID, or Title', required=False, type=str),
        OpenApiParameter(name='type', description='Filter by Activity Type', required=False, type=str),
    ]
)
class HealthPromotionViewSet(viewsets.ModelViewSet):
    queryset = HealthPromotion.objects.all()
    serializer_class = HealthPromotionSerializer
    
    def get_queryset(self):
        qs = super().get_queryset()
        
        search = self.request.query_params.get('search')
        act_type = self.request.query_params.get('type')
        
        if search:
            qs = qs.filter(
                Q(id__icontains=search) |
                Q(promotion_id__icontains=search) |
                Q(title__icontains=search)
            )
        if act_type:
            qs = qs.filter(type__iexact=act_type)
            
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

@extend_schema(
    tags=["Health Promotion"],
    parameters=[
        OpenApiParameter(name='search', description='Search by ID, Promotion ID, or Title', required=False, type=str),
        OpenApiParameter(name='type', description='Filter by Activity Type', required=False, type=str),
    ]
)
class PostActivityViewSet(viewsets.ModelViewSet):
    queryset = PostActivity.objects.all()
    serializer_class = PostActivitySerializer

    def get_queryset(self):
        qs = super().get_queryset()
        
        search = self.request.query_params.get('search')
        act_type = self.request.query_params.get('type')
        
        if search:
            qs = qs.filter(
                Q(id__icontains=search) |
                Q(health_promotion__promotion_id__icontains=search) |
                Q(health_promotion__title__icontains=search)
            )
        if act_type:
            qs = qs.filter(health_promotion__type__iexact=act_type)
            
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

@extend_schema(
    tags=["CHEW Reporting"],
    summary="Get CHEW Stats (New Registrations, Community Visits, Maternal Follow ups, Health Promotion)",
    parameters=[
        OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
    ]
)
class ChewStatsView(APIView):
    def get(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        users_qs = User.objects.filter(role='PATIENT', created_by__role='CHEW', created_by__facility=request.user.facility)
        visits_qs = Appointment.objects.filter(visit_type='COMMUNITY', assigned_to__role='CHEW', facility=request.user.facility)
        anc_qs = ANCVisit.objects.filter(created_by__role='CHEW', appointment__facility=request.user.facility)
        pnc_qs = PNCVisit.objects.filter(created_by__role='CHEW', appointment__facility=request.user.facility)
        hp_qs = HealthPromotion.objects.filter(created_by__role='CHEW')

        if start_date:
            users_qs = users_qs.filter(created_at__date__gte=start_date)
            visits_qs = visits_qs.filter(created_at__date__gte=start_date)
            anc_qs = anc_qs.filter(created_at__date__gte=start_date)
            pnc_qs = pnc_qs.filter(created_at__date__gte=start_date)
            hp_qs = hp_qs.filter(created_at__date__gte=start_date)
        if end_date:
            users_qs = users_qs.filter(created_at__date__lte=end_date)
            visits_qs = visits_qs.filter(created_at__date__lte=end_date)
            anc_qs = anc_qs.filter(created_at__date__lte=end_date)
            pnc_qs = pnc_qs.filter(created_at__date__lte=end_date)
            hp_qs = hp_qs.filter(created_at__date__lte=end_date)

        data = {
            "new_registrations": users_qs.count(),
            "community_visits": visits_qs.count(),
            "maternal_follow_ups": anc_qs.count() + pnc_qs.count(),
            "health_promotions": hp_qs.count()
        }
        return Response(data)

@extend_schema(
    tags=["CHEW Reporting"],
    summary="Get Health Promotions scheduled for today"
)
class HealthPromotionsTodayView(generics.ListAPIView):
    serializer_class = HealthPromotionTodaySerializer
    pagination_class = None

    def get_queryset(self):
        today = timezone.now().date()
        return HealthPromotion.objects.filter(start_date__date=today).order_by('start_date')


@extend_schema(
    tags=["CHEW Reporting"],
    summary="Get CHEW Activity Report Stats",
    parameters=[
        OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
    ]
)
class ChewActivityReportStatsView(APIView):
    def get(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        users_qs = User.objects.filter(role='PATIENT', created_by__role='CHEW', created_by__facility=request.user.facility)
        appt_qs = Appointment.objects.filter(assigned_to__role='CHEW', facility=request.user.facility)
        anc_qs = ANCVisit.objects.filter(created_by__role='CHEW', appointment__facility=request.user.facility)
        pnc_qs = PNCVisit.objects.filter(created_by__role='CHEW', appointment__facility=request.user.facility)
        community_qs = appt_qs.filter(visit_type='COMMUNITY')
        hp_qs = HealthPromotion.objects.filter(created_by__role='CHEW')
        pa_qs = PostActivity.objects.filter(created_by__role='CHEW')

        if start_date:
            users_qs = users_qs.filter(created_at__date__gte=start_date)
            appt_qs = appt_qs.filter(created_at__date__gte=start_date)
            anc_qs = anc_qs.filter(created_at__date__gte=start_date)
            pnc_qs = pnc_qs.filter(created_at__date__gte=start_date)
            community_qs = community_qs.filter(created_at__date__gte=start_date)
            hp_qs = hp_qs.filter(created_at__date__gte=start_date)
            pa_qs = pa_qs.filter(created_at__date__gte=start_date)
            
        if end_date:
            users_qs = users_qs.filter(created_at__date__lte=end_date)
            appt_qs = appt_qs.filter(created_at__date__lte=end_date)
            anc_qs = anc_qs.filter(created_at__date__lte=end_date)
            pnc_qs = pnc_qs.filter(created_at__date__lte=end_date)
            community_qs = community_qs.filter(created_at__date__lte=end_date)
            hp_qs = hp_qs.filter(created_at__date__lte=end_date)
            pa_qs = pa_qs.filter(created_at__date__lte=end_date)

        maternal_count = anc_qs.count() + pnc_qs.count()
        community_count = community_qs.count()

        patients_registered = set(users_qs.values_list('id', flat=True))
        patients_seen = set(appt_qs.values_list('patient_id', flat=True))
        patients_reached = len(patients_registered.union(patients_seen))

        total_activities = (
            users_qs.count() +
            appt_qs.count() +
            maternal_count +
            hp_qs.count() +
            pa_qs.count()
        )

        data = {
            "total_activities": total_activities,
            "patients_reached": patients_reached,
            "maternal_follow_ups": maternal_count,
            "community_visits": community_count
        }
        return Response(data)


@extend_schema(
    tags=["CHEW Reporting"],
    summary="Get Entire Activity Report List (Paginated)",
    parameters=[
        OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='search', description='Search across items', required=False, type=str),
        OpenApiParameter(name='activity_type', description='Enum: Patient Registration, Maternal Follow ups, Appointment, Health Promotion, Health Promotion Post Activity', required=False, type=str),
    ]
)
class ActivityReportListView(generics.ListAPIView):
    serializer_class = ActivityReportItemSerializer

    def get_queryset(self):
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        search = self.request.query_params.get('search')
        activity_type = self.request.query_params.get('activity_type')
        facility = self.request.user.facility

        q1 = User.objects.filter(role='PATIENT', created_by__isnull=False, created_by__facility=facility).annotate(
            item_id=Cast('id', CharField(max_length=255)),
            activity_type=Value('Patient Registration', CharField(max_length=255)),
            desc_val=Cast('email', CharField(max_length=255)),
            date=F('created_at'),
            performed_by=Concat('created_by__first_name', Value(' '), 'created_by__last_name', output_field=CharField(max_length=255)),
            status_val=Value('COMPLETED', CharField(max_length=255))
        ).values('item_id', 'activity_type', 'desc_val', 'date', 'performed_by', 'status_val')

        q2 = ANCVisit.objects.filter(appointment__facility=facility).annotate(
            item_id=Cast('id', CharField(max_length=255)),
            activity_type=Value('Maternal Follow ups', CharField(max_length=255)),
            desc_val=Cast('appointment__appointment_id', CharField(max_length=255)),
            date=F('created_at'),
            performed_by=Concat('created_by__first_name', Value(' '), 'created_by__last_name', output_field=CharField(max_length=255)),
            status_val=Value('COMPLETED', CharField(max_length=255))
        ).values('item_id', 'activity_type', 'desc_val', 'date', 'performed_by', 'status_val')

        q3 = PNCVisit.objects.filter(appointment__facility=facility).annotate(
            item_id=Cast('id', CharField(max_length=255)),
            activity_type=Value('Maternal Follow ups', CharField(max_length=255)),
            desc_val=Cast('appointment__appointment_id', CharField(max_length=255)),
            date=F('created_at'),
            performed_by=Concat('created_by__first_name', Value(' '), 'created_by__last_name', output_field=CharField(max_length=255)),
            status_val=Value('COMPLETED', CharField(max_length=255))
        ).values('item_id', 'activity_type', 'desc_val', 'date', 'performed_by', 'status_val')

        q4 = Appointment.objects.filter(facility=facility).annotate(
            item_id=Cast('id', CharField(max_length=255)),
            activity_type=Value('Appointment', CharField(max_length=255)),
            desc_val=Cast('appointment_id', CharField(max_length=255)),
            date=F('created_at'),
            performed_by=Concat('created_by__first_name', Value(' '), 'created_by__last_name', output_field=CharField(max_length=255)),
            status_val=Cast('status', CharField(max_length=255))
        ).values('item_id', 'activity_type', 'desc_val', 'date', 'performed_by', 'status_val')

        q5 = HealthPromotion.objects.annotate(
            item_id=Cast('id', CharField(max_length=255)),
            activity_type=Value('Health Promotion', CharField(max_length=255)),
            desc_val=Cast('title', CharField(max_length=255)),
            date=F('created_at'),
            performed_by=Concat('created_by__first_name', Value(' '), 'created_by__last_name', output_field=CharField(max_length=255)),
            status_val=Cast('status', CharField(max_length=255))
        ).values('item_id', 'activity_type', 'desc_val', 'date', 'performed_by', 'status_val')

        q6 = PostActivity.objects.annotate(
            item_id=Cast('id', CharField(max_length=255)),
            activity_type=Value('Health Promotion Post Activity', CharField(max_length=255)),
            desc_val=Cast('health_promotion__title', CharField(max_length=255)),
            date=F('created_at'),
            performed_by=Concat('created_by__first_name', Value(' '), 'created_by__last_name', output_field=CharField(max_length=255)),
            status_val=Cast('status', CharField(max_length=255))
        ).values('item_id', 'activity_type', 'desc_val', 'date', 'performed_by', 'status_val')
        
        def apply_filters(qs, search_text, start_d, end_d, desc_field, name_prefix='created_by'):
            if start_d:
                qs = qs.filter(created_at__date__gte=start_d)
            if end_d:
                qs = qs.filter(created_at__date__lte=end_d)
            if search_text:
                qs = qs.filter(
                    Q(**{f"{desc_field}__icontains": search_text}) | 
                    Q(**{f"{name_prefix}__first_name__icontains": search_text}) |
                    Q(**{f"{name_prefix}__last_name__icontains": search_text})
                )
            return qs

        q1 = apply_filters(q1, search, start_date, end_date, 'email', 'created_by')
        q2 = apply_filters(q2, search, start_date, end_date, 'appointment__appointment_id', 'created_by')
        q3 = apply_filters(q3, search, start_date, end_date, 'appointment__appointment_id', 'created_by')
        q4 = apply_filters(q4, search, start_date, end_date, 'appointment_id', 'created_by')
        q5 = apply_filters(q5, search, start_date, end_date, 'title', 'created_by')
        q6 = apply_filters(q6, search, start_date, end_date, 'health_promotion__title', 'created_by')

        queries = []
        if not activity_type or activity_type == 'Patient Registration': queries.append(q1)
        if not activity_type or activity_type == 'Maternal Follow ups': queries.extend([q2, q3])
        if not activity_type or activity_type == 'Appointment': queries.append(q4)
        if not activity_type or activity_type == 'Health Promotion': queries.append(q5)
        if not activity_type or activity_type == 'Health Promotion Post Activity': queries.append(q6)

        if not queries:
            return User.objects.none()

        combined = queries[0]
        for q in queries[1:]:
            combined = combined.union(q)

        combined = combined.order_by('-date')
        return combined

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        def map_item(item):
            return {
                'id': item['item_id'],
                'activity_type': item['activity_type'],
                'description': item['desc_val'],
                'date': item['date'],
                'performed_by': item['performed_by'],
                'status': item['status_val']
            }

        if page is not None:
            mapped_page = [map_item(x) for x in page]
            serializer = self.get_serializer(mapped_page, many=True)
            return self.get_paginated_response(serializer.data)

        mapped_qs = [map_item(x) for x in queryset]
        serializer = self.get_serializer(mapped_qs, many=True)
        return Response(serializer.data)
