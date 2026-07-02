# consultations/views.py
from rest_framework import viewsets
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.decorators import action
from .models import Consultation
from rest_framework import status
from rest_framework.response import Response
from .serializers import ConsultationReadSerializer, ConsultationCreateSerializer

@extend_schema(tags=["Consultations"])
class ConsultationViewSet(viewsets.ModelViewSet):
    queryset = Consultation.objects.none()

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ConsultationCreateSerializer
        return ConsultationReadSerializer

    @extend_schema(
        summary="List & Filter Consultations",
        parameters=[
            OpenApiParameter(name='patient_id', description='Filter by Patient UUID', required=False, type=str),
            OpenApiParameter(name='appointment_id', description='Filter by Appointment UUID', required=False, type=str),
            OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='search', description='Search by Patient Name, Diagnosis, or Complaint', required=False, type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = Consultation.objects.filter(appointment__facility=self.request.user.facility)

        if self.request.user.role == 'DOCTOR':
            qs = qs.filter(doctor=self.request.user)

        patient_id = self.request.query_params.get('patient_id')
        appt_id = self.request.query_params.get('appointment_id')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        search = self.request.query_params.get('search')

        if patient_id:
            qs = qs.filter(patient__id=patient_id)
        if appt_id:
            qs = qs.filter(appointment__id=appt_id)
        if start_date:
            qs = qs.filter(created_at__gte=start_date)
        if end_date:
            qs = qs.filter(created_at__lte=end_date)
            
        if search:
            qs = qs.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search) |
                Q(primary_diagnosis__icontains=search) |
                Q(chief_complaint__icontains=search)
            )

        return qs.order_by('-created_at')

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @extend_schema(
        summary="Get Consultation by Appointment ID",
        responses={200: ConsultationReadSerializer, 404: dict}
    )
    @action(detail=False, methods=['get'], url_path=r'by-appointment/(?P<appointment_id>[^/.]+)')
    def by_appointment(self, request, appointment_id=None):
        """
        Directly fetches the single consultation object for a specific appointment.
        Returns a 404 if the doctor hasn't conducted the consultation yet.
        """
        try:
            # Ensure the consultation exists AND belongs to the user's facility
            consultation = Consultation.objects.get(
                appointment__id=appointment_id,
                appointment__facility=request.user.facility
            )
            serializer = self.get_serializer(consultation)
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except Consultation.DoesNotExist:
            return Response(
                {"detail": "No consultation has been recorded for this appointment yet."}, 
                status=status.HTTP_404_NOT_FOUND
            )
