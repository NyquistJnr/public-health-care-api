import uuid
from rest_framework import viewsets, status
from rest_framework.response import Response
from django.db import transaction
from django.contrib.auth.models import Group
from drf_spectacular.utils import extend_schema, extend_schema_view
from .models import ImmunizationRecord
from .serializers import FastTrackImmunizationSerializer
from core.models import User, PatientProfile
from appointments.models import Appointment
from inventory.models import DrugBatch, InventoryTransaction

@extend_schema_view(
    create=extend_schema(tags=["Immunization"], summary="Fast-Track Record Vaccine (Auto Patient/Appt/Inventory)"),
)
class ImmunizationViewSet(viewsets.ViewSet):

    @transaction.atomic
    def create(self, request):
        serializer = FastTrackImmunizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        user = request.user
        facility = user.facility
        vaccine_drug = data['vaccine_given']

        active_batches = DrugBatch.objects.filter(
            drug=vaccine_drug, is_active=True, remaining_quantity__gt=0, expiry_date__gte=data['date_of_visit']
        ).select_for_update().order_by('expiry_date')
        
        if sum(b.remaining_quantity for b in active_batches) < 1:
            return Response({"detail": f"Insufficient stock for {vaccine_drug.name}. Please restock inventory."}, status=status.HTTP_400_BAD_REQUEST)

        batch = active_batches.first()
        batch.remaining_quantity -= 1
        batch.save(update_fields=['remaining_quantity', 'updated_at'])
        
        InventoryTransaction.objects.create(
            batch=batch, transaction_type='DISPENSE', quantity=-1, performed_by=user
        )

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
                group = Group.objects.get(name='PATIENT')
                patient_record.groups.add(group)
            except Group.DoesNotExist:
                pass

            PatientProfile.objects.create(
                user=patient_record, created_by=user, sex=new_data['sex'], date_of_birth=new_data['date_of_birth'],
                next_of_kin_name=new_data.get('next_of_kin_name', ''), next_of_kin_phone=new_data.get('next_of_kin_phone', '')
            )

        appointment = Appointment.objects.create(
            facility=facility,
            patient=patient_record,
            assigned_to=user,
            appointment_date=data['date_of_visit'],
            appointment_time="08:00:00",
            visit_type='IMMUNIZATION',
            status='COMPLETED',
            reason_for_visit=f"{vaccine_drug.name} Administration ({data['session_type']})",
            created_by=user
        )

        record = ImmunizationRecord.objects.create(
            patient=patient_record,
            appointment=appointment,
            facility=facility,
            administered_by=user,
            session_type=data['session_type'],
            state=data['state'], lga=data['lga'], ward=data['ward'], site_name=data.get('site_name', ''),
            vaccine_given=vaccine_drug,
            date_of_visit=data['date_of_visit'],
            status='COMPLETED',
            notes=data.get('notes', ''),
            created_by=user
        )

        return Response({
            "detail": "Immunization successfully recorded.",
            "patient_id": patient_record.patient_profile.patient_id,
            "patient_name": f"{patient_record.first_name} {patient_record.last_name}",
            "vaccine": vaccine_drug.name,
            "age_at_vaccination": record.age_at_vaccination
        }, status=status.HTTP_201_CREATED)
