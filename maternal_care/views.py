# maternal_care/views.py
import uuid
import calendar
from datetime import date, timedelta
from django.db import transaction
from django.db.models import Q, OuterRef, Exists
from django.contrib.auth.models import Group
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from drf_spectacular.utils import extend_schema, OpenApiParameter
from core.models import User, PatientProfile
from core.pagination import StandardResultsSetPagination
from .services import MaternalScheduleEngine
from .models import (
    MaternalCareEpisode, ANCVisit, PNCVisit,
    PNCNewbornAssessment, MaternalScheduleRule
)
from .serializers import (
    MaternalCareEpisodeSerializer, ANCVisitSerializer,
    PNCVisitSerializer, PNCNewbornAssessmentSerializer,
    RecordDeliverySerializer, EpisodeBabySerializer,
    MaternalScheduleRuleSerializer, AppointmentForANCSerializer,
    AppointmentForPNCSerializer, PaginatedMaternalFollowUpSerializer,
    DeliverySerializer
)


def _ordinal(n):
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f"{n}{suffix}"


def _due_status(next_visit_date, today):
    delta_days = (next_visit_date - today).days
    if delta_days < 0:
        text = f"{abs(delta_days)} day{'s' if abs(delta_days) != 1 else ''} overdue"
        return 'OVERDUE', delta_days, text
    if delta_days == 0:
        return 'DUE_TODAY', 0, "today"
    return 'UPCOMING', delta_days, f"in {delta_days} day{'s' if delta_days != 1 else ''}"


def _follow_up_tag(due_status, is_high_risk, care_type):
    if due_status == 'OVERDUE':
        return 'Urgent'
    if is_high_risk:
        return 'High risk'
    return 'ANC Due' if care_type == 'ANC' else 'Postnatal'


def _latest_visits_with_pending_followup(model, facility, date_lower_bound, date_upper_bound, search):
    """Returns the most recent visit per episode (i.e. the one whose next_visit_date is still outstanding)."""
    newer_visit_exists = model.objects.filter(
        episode=OuterRef('episode'), visit_sequence_number__gt=OuterRef('visit_sequence_number')
    )
    qs = model.objects.filter(
        episode__patient__facility=facility,
        next_visit_date__isnull=False
    ).annotate(
        has_newer_visit=Exists(newer_visit_exists)
    ).filter(has_newer_visit=False).select_related(
        'episode', 'episode__patient', 'episode__patient__patient_profile'
    )

    if date_lower_bound:
        qs = qs.filter(next_visit_date__gte=date_lower_bound)
    if date_upper_bound:
        qs = qs.filter(next_visit_date__lte=date_upper_bound)
    if search:
        qs = qs.filter(
            Q(episode__patient__first_name__icontains=search) |
            Q(episode__patient__last_name__icontains=search) |
            Q(episode__patient__patient_profile__patient_id__icontains=search)
        )
    return qs


@extend_schema(tags=["Maternal Care Setup - State Admin and Doctor"])
class MaternalScheduleRuleViewSet(viewsets.ModelViewSet):
    """
    Manage the Global/State-wide default settings for ANC and PNC schedules.
    Should be restricted to State Admins or highly privileged users.
    """
    queryset = MaternalScheduleRule.objects.all()
    serializer_class = MaternalScheduleRuleSerializer
    # permission_classes = [HasRequiredPermission]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


@extend_schema(tags=["Maternal Care"])
class MaternalCareEpisodeViewSet(viewsets.ModelViewSet):
    queryset = MaternalCareEpisode.objects.none()
    serializer_class = MaternalCareEpisodeSerializer

    @extend_schema(
        summary="List & Filter Pregnancies (Episodes)",
        parameters=[
            OpenApiParameter(name='search', description='Search by Patient Name or PT-ID', required=False, type=str),
            OpenApiParameter(name='status', description='Filter by Status (ACTIVE, DELIVERED, CLOSED, MISCARRIAGE)', required=False, type=str),
            OpenApiParameter(name='start_date', description='Filter by Follow-up/EDD start date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='end_date', description='Filter by Follow-up/EDD end date (YYYY-MM-DD)', required=False, type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = MaternalCareEpisode.objects.filter(
            patient__facility=self.request.user.facility
        ).select_related('patient__patient_profile')

        search = self.request.query_params.get('search')
        ep_status = self.request.query_params.get('status')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')

        if search:
            qs = qs.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search) |
                Q(patient__patient_profile__patient_id__icontains=search) |
                Q(episode_id__icontains=search)
            )
            
        if ep_status:
            qs = qs.filter(status=ep_status.upper())
            
        if start_date:
            qs = qs.filter(expected_date_of_delivery__gte=start_date)
        if end_date:
            qs = qs.filter(expected_date_of_delivery__lte=end_date)

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @extend_schema(
        summary="Record Delivery & Auto-Register Newborns", 
        request=RecordDeliverySerializer
    )
    @action(detail=True, methods=['post'], url_path='record-delivery')
    @transaction.atomic
    def record_delivery(self, request, pk=None):
        episode = self.get_object()
        
        if episode.status in ['DELIVERED', 'CLOSED']:
            return Response(
                {"detail": "This episode has already been marked as delivered or closed."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = RecordDeliverySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        facility = request.user.facility
        mother = episode.patient
        
        episode.status = 'DELIVERED'
        episode.save(update_fields=['status', 'updated_at'])
        
        created_babies = []
        patient_group = Group.objects.filter(name='PATIENT').first()

        for baby_data in data['babies']:
            dummy_email = f"baby_{uuid.uuid4().hex[:10]}@placeholder.com"
            baby_user = User.objects.create(
                username=dummy_email, email='', first_name=baby_data['first_name'],
                last_name=baby_data['last_name'], role='PATIENT', facility=facility,
                created_by=request.user
            )
            baby_user.set_unusable_password()
            baby_user.save()
            
            if patient_group:
                baby_user.groups.add(patient_group)
                
            PatientProfile.objects.create(
                user=baby_user, sex=baby_data['sex'], date_of_birth=data['delivery_date'],
                mother=mother, birth_episode=episode, 
                delivery_mode=baby_data.get('delivery_mode'),
                birth_status=baby_data.get('birth_status'),
                complications=baby_data.get('complications'),
                created_by=request.user
            )
            
            created_babies.append({
                "patient_id": baby_user.patient_profile.patient_id,
                "name": f"{baby_user.first_name} {baby_user.last_name}",
                "sex": baby_data['sex']
            })

        return Response({
            "detail": f"Delivery recorded successfully. {len(created_babies)} newborn(s) registered.",
            "episode_status": episode.status,
            "registered_babies": created_babies
        }, status=status.HTTP_201_CREATED)
    
    @extend_schema(
        summary="Get all babies born in this Episode", 
        responses=EpisodeBabySerializer(many=True)
    )
    @action(detail=True, methods=['get'], url_path='babies')
    def get_babies(self, request, pk=None):
        """
        Retrieves the registered newborn(s) linked to this pregnancy episode.
        """
        episode = self.get_object()
        babies = User.objects.filter(
            patient_profile__birth_episode=episode,
            facility=request.user.facility
        ).select_related('patient_profile')
        
        serializer = EpisodeBabySerializer(babies, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(tags=["Maternal Care"])
class ANCVisitViewSet(viewsets.ModelViewSet):
    queryset = ANCVisit.objects.none()
    serializer_class = ANCVisitSerializer

    @extend_schema(
        summary="List & Filter ANC Visits",
        parameters=[
            OpenApiParameter(name='episode_id', description='Get ANC visits for a specific Pregnancy Episode', required=False, type=str),
            OpenApiParameter(name='attendance_type', description='NEW or RETURN', required=False, type=str),
            OpenApiParameter(name='start_date', description='Filter by appointment date start', required=False, type=str),
            OpenApiParameter(name='end_date', description='Filter by appointment date end', required=False, type=str),
            OpenApiParameter(name='search', description='Search by Appointment ID, Patient ID, Patient Name, Phone, or Email', required=False, type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = ANCVisit.objects.filter(appointment__facility=self.request.user.facility).select_related(
            'appointment', 'appointment__patient', 'appointment__patient__patient_profile'
        )

        episode_id = self.request.query_params.get('episode_id')
        attendance_type = self.request.query_params.get('attendance_type')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        search = self.request.query_params.get('search')

        if episode_id:
            qs = qs.filter(episode__id=episode_id)
        if attendance_type:
            qs = qs.filter(attendance_type=attendance_type.upper())
        if start_date:
            qs = qs.filter(appointment__appointment_date__gte=start_date)
        if end_date:
            qs = qs.filter(appointment__appointment_date__lte=end_date)
        if search:
            qs = qs.filter(
                Q(appointment__appointment_id__icontains=search) |
                Q(appointment__patient__patient_profile__patient_id__icontains=search) |
                Q(appointment__patient__first_name__icontains=search) |
                Q(appointment__patient__last_name__icontains=search) |
                Q(appointment__patient__phone_number__icontains=search) |
                Q(appointment__patient__email__icontains=search)
            )

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        visit = serializer.save(created_by=self.request.user)
        previous_visits_count = ANCVisit.objects.filter(episode=visit.episode).count()
        visit.visit_sequence_number = previous_visits_count

        next_date, recommended_tasks = MaternalScheduleEngine.calculate_next_visit(
            episode=visit.episode,
            care_type='ANC',
            current_visit_sequence=visit.visit_sequence_number,
            last_visit_date=visit.appointment.appointment_date or timezone.now().date()
        )
        
        visit.next_visit_date = next_date
        visit.recommended_tasks = recommended_tasks
        visit.save(update_fields=['visit_sequence_number', 'next_visit_date', 'recommended_tasks'])


@extend_schema(tags=["Maternal Care"])
class PNCVisitViewSet(viewsets.ModelViewSet):
    queryset = PNCVisit.objects.none()
    serializer_class = PNCVisitSerializer

    @extend_schema(
        summary="List & Filter PNC Visits",
        parameters=[
            OpenApiParameter(name='episode_id', description='Get PNC visits for a specific Pregnancy Episode', required=False, type=str),
            OpenApiParameter(name='outcome', description='TREATED, ADMITTED, or REFERRED', required=False, type=str),
            OpenApiParameter(name='start_date', description='Filter by appointment date start', required=False, type=str),
            OpenApiParameter(name='end_date', description='Filter by appointment date end', required=False, type=str),
            OpenApiParameter(name='search', description='Search by Appointment ID, Patient ID, Patient Name, Phone, or Email', required=False, type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = PNCVisit.objects.filter(appointment__facility=self.request.user.facility).select_related(
            'appointment', 'appointment__patient', 'appointment__patient__patient_profile'
        )

        episode_id = self.request.query_params.get('episode_id')
        outcome = self.request.query_params.get('outcome')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        search = self.request.query_params.get('search')

        if episode_id:
            qs = qs.filter(episode__id=episode_id)
        if outcome:
            qs = qs.filter(outcome=outcome.upper())
        if start_date:
            qs = qs.filter(appointment__appointment_date__gte=start_date)
        if end_date:
            qs = qs.filter(appointment__appointment_date__lte=end_date)
        if search:
            qs = qs.filter(
                Q(appointment__appointment_id__icontains=search) |
                Q(appointment__patient__patient_profile__patient_id__icontains=search) |
                Q(appointment__patient__first_name__icontains=search) |
                Q(appointment__patient__last_name__icontains=search) |
                Q(appointment__patient__phone_number__icontains=search) |
                Q(appointment__patient__email__icontains=search)
            )

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        visit = serializer.save(created_by=self.request.user)

        previous_visits_count = PNCVisit.objects.filter(episode=visit.episode).count()
        visit.visit_sequence_number = previous_visits_count
        
        next_date, recommended_tasks = MaternalScheduleEngine.calculate_next_visit(
            episode=visit.episode,
            care_type='PNC',
            current_visit_sequence=visit.visit_sequence_number,
            last_visit_date=visit.appointment.appointment_date or timezone.now().date()
        )
        
        visit.next_visit_date = next_date
        visit.recommended_tasks = recommended_tasks
        visit.save(update_fields=['visit_sequence_number', 'next_visit_date', 'recommended_tasks'])


@extend_schema(tags=["Maternal Care"])
class PNCNewbornAssessmentViewSet(viewsets.ModelViewSet):
    queryset = PNCNewbornAssessment.objects.none()
    serializer_class = PNCNewbornAssessmentSerializer

    @extend_schema(
        summary="List & Filter Newborn Assessments",
        parameters=[
            OpenApiParameter(name='pnc_visit_id', description='Get all babies assessed in a specific PNC Visit', required=False, type=str),
            OpenApiParameter(name='episode_id', description='Get ALL newborn assessments across the entire Pregnancy Episode', required=False, type=str),
            OpenApiParameter(name='outcome', description='Filter by HEALTHY, ADMITTED, or REFERRED', required=False, type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = PNCNewbornAssessment.objects.filter(
            pnc_visit__appointment__facility=self.request.user.facility
        ).select_related('baby', 'pnc_visit')

        pnc_visit_id = self.request.query_params.get('pnc_visit_id')
        episode_id = self.request.query_params.get('episode_id')
        outcome = self.request.query_params.get('outcome')

        if pnc_visit_id:
            qs = qs.filter(pnc_visit__id=pnc_visit_id)
        if episode_id:
            qs = qs.filter(pnc_visit__episode__id=episode_id)
        if outcome:
            qs = qs.filter(outcome=outcome.upper())

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

@extend_schema(
    tags=["Maternal Care"],
    summary="Unified ANC Encounter (Auto-handles New vs. Returning Patients)",
    description=(
        "Creates an Appointment, an ANC Visit, and (if necessary) a new Pregnancy Episode in one call. "
        "If the patient already has an ACTIVE pregnancy, they are automatically treated as a RETURN patient "
        "and episode fields (LMP, Gravida, Parity) are ignored."
    ),
    request=AppointmentForANCSerializer,
    responses={201: AppointmentForANCSerializer}
)
class AppointmentForANCView(APIView):
    def post(self, request):
        serializer = AppointmentForANCSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        anc_visit = serializer.save()
        
        return Response({
            "status": "success",
            "message": "ANC Encounter recorded successfully.",
            "data": {
                "episode_id": anc_visit.episode.episode_id,
                "attendance_type": anc_visit.attendance_type,
                "appointment_id": anc_visit.appointment.appointment_id,
                "next_visit_date": anc_visit.next_visit_date,
                "visit_sequence_number": anc_visit.visit_sequence_number
            }
        }, status=status.HTTP_201_CREATED)

@extend_schema(
    tags=["Maternal Care"],
    summary="Unified PNC Encounter (Auto-links to Episode & Handles Walk-ins)",
    description=(
        "Creates an Appointment, a PNC Visit, and Baby Assessments in one call. "
        "It automatically links to the mother's DELIVERED episode. "
        "If she is a Walk-in without an episode, provide 'walk_in_delivery_data' to auto-register her past delivery and babies."
    ),
    request=AppointmentForPNCSerializer,
    responses={201: AppointmentForPNCSerializer}
)
class AppointmentForPNCView(APIView):
    def post(self, request):
        serializer = AppointmentForPNCSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        pnc_visit = serializer.save()
        
        return Response({
            "status": "success",
            "message": "PNC Encounter recorded successfully.",
            "data": {
                "episode_id": pnc_visit.episode.episode_id,
                "episode_status": pnc_visit.episode.status,
                "attendance_type": pnc_visit.attendance_type,
                "appointment_id": pnc_visit.appointment.appointment_id,
                "next_visit_date": pnc_visit.next_visit_date,
                "visit_sequence_number": pnc_visit.visit_sequence_number,
                "assessments_recorded": pnc_visit.newborn_assessments.count()
            }
        }, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["Maternal Care"],
    summary="Get Upcoming ANC & PNC Follow-Ups",
    description=(
        "Returns a combined, card-ready feed of outstanding ANC and PNC follow-ups - the next "
        "recommended visit for each pregnancy/postpartum episode, based on its most recent visit."
    ),
    parameters=[
        OpenApiParameter(name='care_type', description='Filter to ANC or PNC only. Omit for both.', required=False, type=str),
        OpenApiParameter(name='days', description='Only show follow-ups due within the next N days (overdue ones are always included).', required=False, type=int),
        OpenApiParameter(name='month', description='Only show follow-ups due within a specific calendar month (YYYY-MM). Takes precedence over `days` if both are passed.', required=False, type=str),
        OpenApiParameter(name='search', description='Search by Patient Name or Patient ID', required=False, type=str),
        OpenApiParameter(name='page', description='Page number', required=False, type=int),
        OpenApiParameter(name='page_size', description='Items per page', required=False, type=int),
    ],
    responses=PaginatedMaternalFollowUpSerializer
)
class UpcomingMaternalFollowUpsView(APIView):
    def get(self, request):
        facility = request.user.facility
        today = timezone.now().date()

        care_type = request.query_params.get('care_type')
        days_param = request.query_params.get('days')
        month_param = request.query_params.get('month')
        search = request.query_params.get('search')

        date_lower_bound = None
        date_upper_bound = None

        if month_param:
            try:
                year, month_num = (int(part) for part in month_param.split('-'))
                date_lower_bound = date(year, month_num, 1)
                date_upper_bound = date(year, month_num, calendar.monthrange(year, month_num)[1])
            except (ValueError, TypeError):
                raise ValidationError({"month": "Must be in YYYY-MM format, e.g. 2026-09."})
        elif days_param:
            try:
                date_upper_bound = today + timedelta(days=int(days_param))
            except (ValueError, TypeError):
                raise ValidationError({"days": "Must be an integer."})

        results = []
        if not care_type or care_type.upper() == 'ANC':
            results.extend(self._build_anc_follow_ups(facility, today, date_lower_bound, date_upper_bound, search))
        if not care_type or care_type.upper() == 'PNC':
            results.extend(self._build_pnc_follow_ups(facility, today, date_lower_bound, date_upper_bound, search))

        results.sort(key=lambda item: item['next_visit_date'])

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(results, request, view=self)
        return paginator.get_paginated_response(page)

    def _build_anc_follow_ups(self, facility, today, date_lower_bound, date_upper_bound, search):
        visits = _latest_visits_with_pending_followup(ANCVisit, facility, date_lower_bound, date_upper_bound, search)

        items = []
        for visit in visits:
            episode = visit.episode
            patient = episode.patient
            patient_name = f"{patient.first_name} {patient.last_name}"
            due_status, due_in_days, due_text = _due_status(visit.next_visit_date, today)
            is_high_risk = bool(visit.risk_factors and visit.risk_factors.strip())
            upcoming_visit_number = visit.visit_sequence_number + 1

            gestational_weeks = None
            if episode.last_menstrual_period:
                gestational_weeks = (visit.next_visit_date - episode.last_menstrual_period).days // 7
            weeks_text = f"{gestational_weeks} weeks" if gestational_weeks is not None else "Gestational age unknown"

            items.append({
                "care_type": "ANC",
                "visit_id": visit.id,
                "episode_id": episode.episode_id,
                "patient_id": patient.id,
                "patient_name": patient_name,
                "patient_display_id": getattr(patient.patient_profile, 'patient_id', None),
                "next_visit_date": visit.next_visit_date,
                "due_status": due_status,
                "due_in_days": due_in_days,
                "upcoming_visit_number": upcoming_visit_number,
                "gestational_weeks": gestational_weeks,
                "is_high_risk": is_high_risk,
                "tag": _follow_up_tag(due_status, is_high_risk, 'ANC'),
                "title": f"{patient_name} · ANC visit due {due_text}",
                "subtitle": f"{weeks_text} · {_ordinal(upcoming_visit_number)} antenatal visit",
            })
        return items

    def _build_pnc_follow_ups(self, facility, today, date_lower_bound, date_upper_bound, search):
        visits = _latest_visits_with_pending_followup(PNCVisit, facility, date_lower_bound, date_upper_bound, search)

        items = []
        for visit in visits:
            episode = visit.episode
            patient = episode.patient
            patient_name = f"{patient.first_name} {patient.last_name}"
            due_status, due_in_days, due_text = _due_status(visit.next_visit_date, today)
            is_high_risk = visit.outcome in ('ADMITTED', 'REFERRED')
            upcoming_visit_number = visit.visit_sequence_number + 1

            items.append({
                "care_type": "PNC",
                "visit_id": visit.id,
                "episode_id": episode.episode_id,
                "patient_id": patient.id,
                "patient_name": patient_name,
                "patient_display_id": getattr(patient.patient_profile, 'patient_id', None),
                "next_visit_date": visit.next_visit_date,
                "due_status": due_status,
                "due_in_days": due_in_days,
                "upcoming_visit_number": upcoming_visit_number,
                "gestational_weeks": None,
                "is_high_risk": is_high_risk,
                "tag": _follow_up_tag(due_status, is_high_risk, 'PNC'),
                "title": f"{patient_name} · PNC visit due {due_text}",
                "subtitle": f"{visit.timing_of_visit} · {_ordinal(upcoming_visit_number)} postnatal visit",
            })
        return items


@extend_schema(
    tags=["Maternal Care - Deliveries"],
    parameters=[
        OpenApiParameter(name='episode_id', description='Filter by raw Pregnancy Episode UUID', required=False, type=str),
    ]
)
class DeliveryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Endpoint to list and retrieve delivery records (babies born).
    """
    serializer_class = DeliverySerializer

    def get_queryset(self):
        # Return all patient profiles that have a birth episode
        qs = PatientProfile.objects.filter(
            birth_episode__isnull=False,
            user__facility=self.request.user.facility
        ).select_related('user', 'mother', 'mother__patient_profile').order_by('-date_of_birth')

        episode_id = self.request.query_params.get('episode_id')
        if episode_id:
            qs = qs.filter(birth_episode__id=episode_id)

        return qs
