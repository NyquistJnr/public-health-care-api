import uuid
from rest_framework import viewsets, status, serializers
from rest_framework.response import Response
from django.db import transaction
from django.contrib.auth.models import Group
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer, OpenApiParameter
from .models import ImmunizationRecord
from .serializers import FastTrackImmunizationSerializer, ImmunizationReadSerializer, ImmunizationUpdateSerializer
from core.models import User, PatientProfile
from appointments.models import Appointment
from inventory.models import ItemBatch, InventoryTransaction
from inventory.services import ScheduleEngine
from django.db.models import Q

@extend_schema_view(
    list=extend_schema(tags=["Immunization"], summary="List all facility immunizations"),
    retrieve=extend_schema(tags=["Immunization"], summary="Get specific immunization record"),
    update=extend_schema(tags=["Immunization"], summary="Update safe fields (Status, Location, Notes)"),
    partial_update=extend_schema(tags=["Immunization"], summary="Partial update safe fields"),
    destroy=extend_schema(tags=["Immunization"], summary="Soft-delete an immunization record"),
    
    create=extend_schema(
        tags=["Immunization"], 
        summary="Fast-Track Record Vaccine (Auto Patient/Appt/Inventory)",
        request=FastTrackImmunizationSerializer,
        responses={
            201: inline_serializer(
                name='ImmunizationSuccessResponse',
                fields={
                    'detail': serializers.CharField(),
                    'patient_id': serializers.CharField(),
                    'patient_name': serializers.CharField(),
                    'vaccine': serializers.CharField(),
                    'age_at_vaccination': serializers.CharField(),
                }
            )
        }
    ),
)
class ImmunizationViewSet(viewsets.ModelViewSet):
    queryset = ImmunizationRecord.objects.none()

    def get_serializer_class(self):
        """Dynamically switch serializers based on the requested action"""
        if self.action == 'create':
            return FastTrackImmunizationSerializer
        elif self.action in ['update', 'partial_update']:
            return ImmunizationUpdateSerializer
        return ImmunizationReadSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter(name='patient_id', description='Filter by exact Patient UUID', required=False, type=str),
            OpenApiParameter(name='status', description='Filter by Status (COMPLETED, PENDING)', required=False, type=str),
            OpenApiParameter(name='vaccine_id', description='Filter by Vaccine/Drug UUID', required=False, type=str),
            OpenApiParameter(name='session_type', description='Filter by Session Type (FIXED, OUTREACH, MOBILE)', required=False, type=str),
            OpenApiParameter(name='start_date', description='Filter from this visit date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='end_date', description='Filter up to this visit date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='search', description='Search by Patient Name or PT-ID', required=False, type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        """Ensure staff only see records from their own facility"""
        qs = ImmunizationRecord.objects.filter(
            facility=self.request.user.facility
        ).select_related('patient', 'vaccine_given', 'administered_by')

        patient_id = self.request.query_params.get('patient_id')
        status_param = self.request.query_params.get('status')
        vaccine_id = self.request.query_params.get('vaccine_id')
        session_type = self.request.query_params.get('session_type')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        search = self.request.query_params.get('search')

        if patient_id:
            qs = qs.filter(patient__id=patient_id)
        if status_param:
            qs = qs.filter(status=status_param.upper())
        if vaccine_id:
            qs = qs.filter(vaccine_given__id=vaccine_id)
        if session_type:
            qs = qs.filter(session_type=session_type.upper())

        if start_date:
            qs = qs.filter(date_of_visit__gte=start_date)
        if end_date:
            qs = qs.filter(date_of_visit__lte=end_date)
            
        if search:
            qs = qs.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search) |
                Q(patient__patient_profile__patient_id__icontains=search)
            )

        return qs.order_by('-date_of_visit', '-created_at')

    @transaction.atomic
    def create(self, request):
        serializer = FastTrackImmunizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        user = request.user
        facility = user.facility
        vaccines_to_give = data['vaccines_given_ids']

        patient_record = None
        if data.get('patient_id'):
            try:
                profile = PatientProfile.objects.get(patient_id=data['patient_id'], user__facility=facility)
                patient_record = profile.user
            except PatientProfile.DoesNotExist:
                return Response({"patient_id": "Patient not found in this facility."}, status=status.HTTP_404_NOT_FOUND)
        else:
            new_data = data['new_patient_data']
            email_dummy = f"patient_{uuid.uuid4().hex[:10]}@placeholder.com"
            patient_record = User.objects.create(
                username=email_dummy, email='', first_name=new_data['first_name'], last_name=new_data['last_name'],
                role='PATIENT', facility=facility
            )
            patient_record.set_unusable_password()
            patient_record.save()
            
            try:
                patient_record.groups.add(Group.objects.get(name='PATIENT'))
            except Group.DoesNotExist:
                pass

            PatientProfile.objects.create(
                user=patient_record, created_by=user, sex=new_data['sex'], date_of_birth=new_data['date_of_birth'],
                next_of_kin_name=new_data.get('next_of_kin_name', ''), 
                next_of_kin_phone=new_data.get('next_of_kin_phone', ''),
                next_of_kin_relationship=new_data.get('next_of_kin_relationship', '')
            )

        for vaccine in vaccines_to_give:
            active_batches = ItemBatch.objects.filter(
                item=vaccine, is_active=True, remaining_quantity__gt=0, expiry_date__gte=data['date_of_visit']
            )
            if sum(b.remaining_quantity for b in active_batches) < 1:
                return Response({"detail": f"Insufficient stock for {vaccine.name}. Aborting all."}, status=status.HTTP_400_BAD_REQUEST)

        vaccine_names = ", ".join([v.name for v in vaccines_to_give])
        appointment = Appointment.objects.create(
            facility=facility,
            patient=patient_record,
            assigned_to=user,
            appointment_date=data['date_of_visit'],
            appointment_time="08:00:00",
            visit_type='IMMUNIZATION',
            status='COMPLETED',
            reason_for_visit=f"Vaccinations administered: {vaccine_names}",
            created_by=user
        )

        administered_details = []
        for vaccine in vaccines_to_give:
            batch = ItemBatch.objects.filter(
                item=vaccine, is_active=True, remaining_quantity__gt=0, expiry_date__gte=data['date_of_visit']
            ).select_for_update().order_by('expiry_date').first()
            
            batch.remaining_quantity -= 1
            batch.save(update_fields=['remaining_quantity', 'updated_at'])
            
            InventoryTransaction.objects.create(
                batch=batch, transaction_type='DISPENSE', quantity=-1, performed_by=user
            )

            previous_doses = ImmunizationRecord.objects.filter(
                patient=patient_record, vaccine_given=vaccine
            ).count()
            current_dose_number = previous_doses + 1

            calculated_next_date = ScheduleEngine.calculate_next_due_date(
                schedule_rules=vaccine.schedule_rules,
                previous_doses_count=previous_doses,
                last_dose_date=data['date_of_visit']
            )

            record = ImmunizationRecord.objects.create(
                patient=patient_record,
                appointment=appointment,
                facility=facility,
                administered_by=user,
                session_type=data['session_type'],
                state=data['state'], lga=data['lga'], ward=data['ward'], site_name=data.get('site_name', ''),
                vaccine_given=vaccine,
                dose_number=current_dose_number,
                next_due_date=calculated_next_date,
                date_of_visit=data['date_of_visit'],
                status='COMPLETED',
                notes=data.get('notes', ''),
                created_by=user
            )

            administered_details.append({
                "vaccine": vaccine.name,
                "dose_number": current_dose_number,
                "next_due_date": calculated_next_date
            })

        return Response({
            "detail": "Immunizations successfully recorded.",
            "patient_id": patient_record.patient_profile.patient_id,
            "patient_name": f"{patient_record.first_name} {patient_record.last_name}",
            "age_at_vaccination": record.age_at_vaccination,
            "administered": administered_details
        }, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        """Utilizes your BaseModel's soft delete to maintain the clinical audit log"""
        instance.delete(deleted_by=self.request.user)
