from rest_framework import viewsets
from drf_spectacular.utils import extend_schema
from .models import MaternalCareEpisode, ANCVisit, PNCVisit, PNCNewbornAssessment
from .serializers import (
    MaternalCareEpisodeSerializer, ANCVisitSerializer, 
    PNCVisitSerializer, PNCNewbornAssessmentSerializer
)

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
