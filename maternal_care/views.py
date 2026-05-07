import uuid
from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema
from .models import MaternalCareEpisode, ANCVisit, PNCVisit, PNCNewbornAssessment
from .serializers import (
    MaternalCareEpisodeSerializer, ANCVisitSerializer, 
    PNCVisitSerializer, PNCNewbornAssessmentSerializer,
    RecordDeliverySerializer
)
from core.models import User, PatientProfile

@extend_schema(tags=["Maternal Care"])
class MaternalCareEpisodeViewSet(viewsets.ModelViewSet):
    queryset = MaternalCareEpisode.objects.all()
    serializer_class = MaternalCareEpisodeSerializer

    def get_queryset(self):
        return MaternalCareEpisode.objects.filter(
            patient__facility=self.request.user.facility
        ).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @extend_schema(
        tags=["Maternal Care"], 
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
        
        try:
            patient_group = Group.objects.get(name='PATIENT')
        except Group.DoesNotExist:
            patient_group = None

        for baby_data in data['babies']:
            dummy_email = f"baby_{uuid.uuid4().hex[:10]}@placeholder.com"
            
            baby_user = User.objects.create(
                username=dummy_email,
                email='',
                first_name=baby_data['first_name'],
                last_name=baby_data['last_name'],
                role='PATIENT',
                facility=facility,
                created_by=request.user
            )
            baby_user.set_unusable_password()
            baby_user.save()
            
            if patient_group:
                baby_user.groups.add(patient_group)
                
            PatientProfile.objects.create(
                user=baby_user,
                sex=baby_data['sex'],
                date_of_birth=data['delivery_date'],
                mother=mother,
                birth_episode=episode,
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


@extend_schema(tags=["Maternal Care"])
class ANCVisitViewSet(viewsets.ModelViewSet):
    queryset = ANCVisit.objects.all()
    serializer_class = ANCVisitSerializer

    def get_queryset(self):
        return ANCVisit.objects.filter(
            appointment__facility=self.request.user.facility
        ).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


@extend_schema(tags=["Maternal Care"])
class PNCVisitViewSet(viewsets.ModelViewSet):
    queryset = PNCVisit.objects.all()
    serializer_class = PNCVisitSerializer

    def get_queryset(self):
        return PNCVisit.objects.filter(
            appointment__facility=self.request.user.facility
        ).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


@extend_schema(tags=["Maternal Care"])
class PNCNewbornAssessmentViewSet(viewsets.ModelViewSet):
    queryset = PNCNewbornAssessment.objects.all()
    serializer_class = PNCNewbornAssessmentSerializer

    def get_queryset(self):
        return PNCNewbornAssessment.objects.filter(
            pnc_visit__appointment__facility=self.request.user.facility
        ).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
