# adverse_events/views.py
from rest_framework import viewsets, status
from rest_framework.response import Response
from django.db.models import Q
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from .models import AdverseEvent
from .serializers import AdverseEventSerializer, AdverseEventDetailSerializer, AdverseEventWriteSerializer


@extend_schema_view(
    list=extend_schema(tags=["Adverse Events"], summary="List & Filter Adverse Drug Events"),
    create=extend_schema(tags=["Adverse Events"], summary="Report a New Adverse Drug Event"),
    retrieve=extend_schema(tags=["Adverse Events"], summary="Get Adverse Event Details"),
    update=extend_schema(tags=["Adverse Events"], summary="Update Adverse Event"),
    partial_update=extend_schema(tags=["Adverse Events"], summary="Partial Update (e.g. Status)"),
    destroy=extend_schema(tags=["Adverse Events"], summary="Delete Adverse Event"),
)
class AdverseEventViewSet(viewsets.ModelViewSet):
    queryset = AdverseEvent.objects.none()

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return AdverseEventWriteSerializer
        if self.action == 'retrieve':
            return AdverseEventDetailSerializer
        return AdverseEventSerializer

    @extend_schema(
        summary="List & Filter Adverse Drug Events",
        parameters=[
            OpenApiParameter(name='patient_id', description='Filter by Patient UUID', required=False, type=str),
            OpenApiParameter(name='status', description='REPORTED, UNDER_REVIEW, RESOLVED, CLOSED', required=False, type=str),
            OpenApiParameter(name='severity', description='MILD, MODERATE, SEVERE, LIFE_THREATENING, FATAL', required=False, type=str),
            OpenApiParameter(name='start_date', description='Filter from date of reaction (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='end_date', description='Filter to date of reaction (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='search', description='Search by Patient Name, Patient ID, Event ID, or Suspected Drug', required=False, type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = AdverseEvent.objects.filter(patient__facility=self.request.user.facility).select_related(
            'patient', 'patient__patient_profile', 'reported_by', 'suspected_drug'
        )

        patient_id = self.request.query_params.get('patient_id')
        event_status = self.request.query_params.get('status')
        severity = self.request.query_params.get('severity')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        search = self.request.query_params.get('search')

        if patient_id:
            qs = qs.filter(patient__id=patient_id)
        if event_status:
            qs = qs.filter(status=event_status.upper())
        if severity:
            qs = qs.filter(severity=severity.upper())
        if start_date:
            qs = qs.filter(date_of_reaction__gte=start_date)
        if end_date:
            qs = qs.filter(date_of_reaction__lte=end_date)

        if search:
            qs = qs.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search) |
                Q(patient__patient_profile__patient_id__icontains=search) |
                Q(event_id__icontains=search) |
                Q(suspected_drug__name__icontains=search)
            )

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        instance.delete(deleted_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance_id, event_id = instance.id, instance.event_id
        self.perform_destroy(instance)
        return Response({"id": instance_id, "event_id": event_id}, status=status.HTTP_200_OK)
