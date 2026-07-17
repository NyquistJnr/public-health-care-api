# appointments/views.py

from rest_framework import viewsets, status as drf_status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from rest_framework.exceptions import ValidationError
from django.db.models import Q
from .models import Appointment, Vitals
from .serializers import (
    AppointmentReadSerializer, AppointmentWriteSerializer, AppointmentStatusUpdateSerializer,
    AppointmentAssignSerializer, VitalsSerializer
)

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
            OpenApiParameter(name='search', description='Search by Patient Name, Patient ID, or Appointment ID', required=False, type=str),
            OpenApiParameter(name='start_date', description='Filter by start date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='end_date', description='Filter by end date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='visit_type', description='Filter by visit type (e.g., GENERAL, FOLLOW_UP, ANTENATAL, IMMUNIZATION, EMERGENCY, OTHER)', required=False, type=str),
            OpenApiParameter(name='status', description='Filter by status (e.g., SCHEDULED, COMPLETED, IN_PROGRESS, CANCELLED, NO_SHOW)', required=False, type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = Appointment.objects.filter(facility=self.request.user.facility).select_related('patient', 'assigned_to', 'created_by')

        search = self.request.query_params.get('search')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        visit_type = self.request.query_params.get('visit_type')
        apt_status = self.request.query_params.get('status')

        if search:
            qs = qs.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search) |
                Q(patient__patient_profile__patient_id__icontains=search) |
                Q(appointment_id__icontains=search)
            )

        if start_date:
            qs = qs.filter(appointment_date__gte=start_date)
        if end_date:
            qs = qs.filter(appointment_date__lte=end_date)

        if visit_type:
            qs = qs.filter(visit_type=visit_type.upper())
        if apt_status:
            qs = qs.filter(status=apt_status.upper())

        return qs.order_by('appointment_date', 'appointment_time')

    def perform_create(self, serializer):
        user = self.request.user
        if not getattr(user, 'facility', None):
            raise ValidationError({
                "detail": "Your account is not assigned to a specific facility. Only facility-level staff can book appointments."
            })

        serializer.save(
            facility=user.facility,
            created_by=user,
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

    @extend_schema(
        tags=["Appointments"],
        summary="Assign HCP After Vitals (Nurse Handoff)",
        description=(
            "Hands an appointment off to a Doctor/Nurse once vitals are done. Only valid on "
            "appointments currently in VITALS_DONE status; on success, moves status to IN_CONSULTATION."
        ),
        request=AppointmentAssignSerializer,
    )
    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        appointment = self.get_object()

        if appointment.status != 'VITALS_DONE':
            raise ValidationError({
                "detail": "Vitals must be completed before a Doctor/Nurse can be assigned to this appointment."
            })

        serializer = AppointmentAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        staff = serializer.validated_data['assigned_to']

        if staff.facility_id != appointment.facility_id:
            raise ValidationError({"assigned_to": "This staff member does not belong to the appointment's facility."})

        appointment.assigned_to = staff
        appointment.status = 'IN_CONSULTATION'
        appointment.updated_by = request.user
        appointment.save(update_fields=['assigned_to', 'status', 'updated_at', 'updated_by'])

        return Response(AppointmentReadSerializer(appointment).data, status=drf_status.HTTP_200_OK)

    @extend_schema(
        tags=["Appointments"], 
        summary="Get My Assigned Appointments (Staff Dashboard)",
        parameters=[
            OpenApiParameter(name='search', description='Search by Patient Name, ID, or Appointment ID', required=False, type=str),
            OpenApiParameter(name='start_date', description='Filter by start date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='end_date', description='Filter by end date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='visit_type', description='Filter by visit type', required=False, type=str),
            OpenApiParameter(name='status', description='Filter by status', required=False, type=str),
        ]
    )
    @action(detail=False, methods=['get'], url_path='my-appointments')
    def my_appointments(self, request):
        """
        Returns a paginated list of appointments specifically assigned to the 
        currently logged-in staff member (Doctor/Nurse).
        """
        qs = Appointment.objects.filter(
            facility=request.user.facility,
            assigned_to=request.user
        ).select_related('patient', 'assigned_to', 'created_by')

        search = request.query_params.get('search')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        visit_type = request.query_params.get('visit_type')
        apt_status = request.query_params.get('status')

        if search:
            qs = qs.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search) |
                Q(patient__patient_profile__patient_id__icontains=search) |
                Q(appointment_id__icontains=search)
            )

        if start_date:
            qs = qs.filter(appointment_date__gte=start_date)
        if end_date:
            qs = qs.filter(appointment_date__lte=end_date)

        if visit_type:
            qs = qs.filter(visit_type=visit_type.upper())
        if apt_status:
            qs = qs.filter(status=apt_status.upper())

        qs = qs.order_by('appointment_date', 'appointment_time')

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        tags=["Appointments"],
        summary="Get Appointments Awaiting Vitals",
        description="Returns appointments that have been assigned to a staff member for vitals and are awaiting vitals.",
        parameters=[
            OpenApiParameter(name='assigned_to_me', description='If true, only returns appointments assigned for vitals to the logged-in user', required=False, type=bool),
            OpenApiParameter(name='search', description='Search by Patient Name, ID, or Appointment ID', required=False, type=str),
        ]
    )
    @action(detail=False, methods=['get'], url_path='awaiting-vitals')
    def awaiting_vitals(self, request):
        qs = Appointment.objects.filter(
            facility=request.user.facility,
            assigned_for_vitals__isnull=False,
            status__in=['SCHEDULED', 'ARRIVED']
        ).select_related('patient', 'assigned_for_vitals', 'created_by')

        if request.query_params.get('assigned_to_me', '').lower() == 'true':
            qs = qs.filter(assigned_for_vitals=request.user)

        search = request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search) |
                Q(patient__patient_profile__patient_id__icontains=search) |
                Q(appointment_id__icontains=search)
            )

        qs = qs.order_by('appointment_date', 'appointment_time')

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

@extend_schema_view(
    list=extend_schema(tags=["Patient Vitals"], summary="List all facility vitals"),
    create=extend_schema(tags=["Patient Vitals"], summary="Record new patient vitals"),
    retrieve=extend_schema(tags=["Patient Vitals"], summary="Get specific vital record"),
    update=extend_schema(tags=["Patient Vitals"], summary="Update vital record"),
    partial_update=extend_schema(tags=["Patient Vitals"], summary="Partial update vitals"),
    destroy=extend_schema(tags=["Patient Vitals"], summary="Delete vital record"),
)
class VitalsViewSet(viewsets.ModelViewSet):
    queryset = Vitals.objects.none()
    serializer_class = VitalsSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter(name='appointment_id', description='Filter by appointment UUID', required=False, type=str),
            OpenApiParameter(name='patient_id', description='Filter by patient UUID', required=False, type=str),
            OpenApiParameter(name='search', description='Search by Patient Name, PT-ID, or Vital ID', required=False, type=str),
            OpenApiParameter(name='visit_type', description='Filter by Appointment Visit Type (e.g., GENERAL, ANTENATAL)', required=False, type=str),
            OpenApiParameter(name='priority', description='Filter by Appointment Priority (NORMAL, URGENT, CRITICAL)', required=False, type=str),
            OpenApiParameter(name='status', description=(
                'Filter by Appointment Status (e.g., SCHEDULED, ARRIVED, VITALS_DONE, COMPLETED). '
                'If omitted, returns vitals for all statuses.'
            ), required=False, type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = Vitals.objects.filter(
            appointment__facility=self.request.user.facility
        ).select_related('patient', 'appointment', 'patient__patient_profile')

        apt_id = self.request.query_params.get('appointment_id')
        pat_id = self.request.query_params.get('patient_id')
        search = self.request.query_params.get('search')
        visit_type = self.request.query_params.get('visit_type')
        priority = self.request.query_params.get('priority')
        apt_status = self.request.query_params.get('status')

        if apt_id:
            qs = qs.filter(appointment_id=apt_id)
        if pat_id:
            qs = qs.filter(patient_id=pat_id)
        if visit_type:
            qs = qs.filter(appointment__visit_type=visit_type.upper())
        if priority:
            qs = qs.filter(appointment__priority=priority.upper())

        if apt_status and apt_status.upper() != 'ALL':
            qs = qs.filter(appointment__status=apt_status.upper())

        if search:
            qs = qs.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search) |
                Q(patient__patient_profile__patient_id__icontains=search) |
                Q(vital_id__icontains=search)
            )

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        appointment = serializer.validated_data.get('appointment')
        serializer.save(
            created_by=self.request.user,
            patient=appointment.patient if appointment else None
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)
