from rest_framework import viewsets, status as drf_status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from django.db.models import Q
from .models import Appointment
from .serializers import AppointmentReadSerializer, AppointmentWriteSerializer, AppointmentStatusUpdateSerializer

@extend_schema_view(
    list=extend_schema(tags=["Appointments"], summary="List all facility appointments"),
    create=extend_schema(tags=["Appointments"], summary="Book a new appointment"),
    retrieve=extend_schema(tags=["Appointments"], summary="Get appointment details"),
    update=extend_schema(tags=["Appointments"], summary="Update appointment details"),
    partial_update=extend_schema(tags=["Appointments"], summary="Partial update"),
    destroy=extend_schema(tags=["Appointments"], summary="Cancel/Delete appointment"),
)
class AppointmentViewSet(viewsets.ModelViewSet):
    queryset = Appointment.objects.none()

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return AppointmentWriteSerializer
        return AppointmentReadSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter(name='date', description='Filter by date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='status', description='Filter by status (e.g., SCHEDULED)', required=False, type=str),
            OpenApiParameter(name='patient_id', description='Filter by patient UUID', required=False, type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = Appointment.objects.filter(facility=self.request.user.facility).select_related('patient', 'assigned_to', 'created_by')

        apt_date = self.request.query_params.get('date')
        apt_status = self.request.query_params.get('status')
        patient_id = self.request.query_params.get('patient_id')

        if apt_date:
            qs = qs.filter(appointment_date=apt_date)
        if apt_status:
            qs = qs.filter(status=apt_status.upper())
        if patient_id:
            qs = qs.filter(patient__id=patient_id)

        return qs.order_by('appointment_date', 'appointment_time')

    def perform_create(self, serializer):
        serializer.save(
            facility=self.request.user.facility,
            created_by=self.request.user,
            status='SCHEDULED'
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @extend_schema(tags=["Appointments"], summary="Update Appointment Status (e.g., Mark Completed/Cancelled)", request=AppointmentStatusUpdateSerializer)
    @action(detail=True, methods=['patch'], url_path='update-status')
    def update_status(self, request, pk=None):
        appointment = self.get_object()
        serializer = AppointmentStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data['status']
        appointment.status = new_status
        appointment.updated_by = request.user
        appointment.save(update_fields=['status', 'updated_at', 'updated_by'])

        return Response({
            "detail": f"Appointment status updated to {new_status}.",
            "status": new_status
        }, status=drf_status.HTTP_200_OK)
