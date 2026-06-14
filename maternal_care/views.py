# maternal_care/views.py

import uuid
from django.db import transaction
from django.db.models import Q
from django.contrib.auth.models import Group
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from core.models import User, PatientProfile
from .models import MaternalCareEpisode, ANCVisit, PNCVisit, PNCNewbornAssessment
from .serializers import (
    MaternalCareEpisodeSerializer, ANCVisitSerializer, 
    PNCVisitSerializer, PNCNewbornAssessmentSerializer,
    RecordDeliverySerializer, EpisodeBabySerializer
)

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
                mother=mother, birth_episode=episode, created_by=request.user
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
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = ANCVisit.objects.filter(appointment__facility=self.request.user.facility)

        episode_id = self.request.query_params.get('episode_id')
        attendance_type = self.request.query_params.get('attendance_type')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')

        if episode_id:
            qs = qs.filter(episode__id=episode_id)
        if attendance_type:
            qs = qs.filter(attendance_type=attendance_type.upper())
        if start_date:
            qs = qs.filter(appointment__appointment_date__gte=start_date)
        if end_date:
            qs = qs.filter(appointment__appointment_date__lte=end_date)

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


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
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = PNCVisit.objects.filter(appointment__facility=self.request.user.facility)

        episode_id = self.request.query_params.get('episode_id')
        outcome = self.request.query_params.get('outcome')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')

        if episode_id:
            qs = qs.filter(episode__id=episode_id)
        if outcome:
            qs = qs.filter(outcome=outcome.upper())
        if start_date:
            qs = qs.filter(appointment__appointment_date__gte=start_date)
        if end_date:
            qs = qs.filter(appointment__appointment_date__lte=end_date)

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


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
