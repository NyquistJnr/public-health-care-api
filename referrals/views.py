# referrals/views.py
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter, inline_serializer
from .models import Referral
from .serializers import (
    ReferralReadSerializer, ReferralCreateSerializer, ReferralStatusUpdateSerializer,
    ReferralAppointmentSummarySerializer, ReferralVitalsSummarySerializer,
    ReferralConsultationSummarySerializer, ReferralPatientProfileSummarySerializer,
)
from appointments.models import Appointment, Vitals
from consultations.models import Consultation
from core.tasks import dispatch_external_referral

@extend_schema(tags=["Patient Referrals"])
class ReferralViewSet(viewsets.ModelViewSet):
    queryset = Referral.objects.none()

    def get_serializer_class(self):
        if self.action == 'create':
            return ReferralCreateSerializer
        return ReferralReadSerializer

    def perform_create(self, serializer):
        referral = serializer.save(created_by=self.request.user)

        if referral.destination_level in ['SECONDARY', 'HIGHER', 'OTHER']:
            request_host = self.request.get_host()
            dispatch_external_referral(referral.id, request_host)

    @extend_schema(
        summary="List & Filter Referrals (Inbound & Outbound)",
        parameters=[
            OpenApiParameter(name='appointment_id', description='Filter by a specific Appointment UUID', required=False, type=str),
            OpenApiParameter(name='direction', description="'inbound' (Received) or 'outbound' (Sent). Defaults to 'outbound'.", required=False, type=str),
            OpenApiParameter(name='status', description='PENDING, ACCEPTED, REJECTED', required=False, type=str),
            OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='search', description='Search by Patient Name or PT-ID', required=False, type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        facility = self.request.user.facility
        direction = self.request.query_params.get('direction', 'outbound').lower()

        if direction == 'inbound':
            qs = Referral.objects.filter(receiving_facility=facility)
        else:
            qs = Referral.objects.filter(referring_facility=facility)

        appt_id = self.request.query_params.get('appointment_id')
        ref_status = self.request.query_params.get('status')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        search = self.request.query_params.get('search')

        if appt_id:
            qs = qs.filter(appointment__id=appt_id)
        if ref_status:
            qs = qs.filter(status=ref_status.upper())
        if start_date:
            qs = qs.filter(created_at__gte=start_date)
        if end_date:
            qs = qs.filter(created_at__lte=end_date)
            
        if search:
            qs = qs.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search) |
                Q(patient__patient_profile__patient_id__icontains=search) |
                Q(referral_id__icontains=search)
            )

        return qs.order_by('-created_at')

    @extend_schema(summary="Accept or Reject an Inbound Referral", request=ReferralStatusUpdateSerializer)
    @action(detail=True, methods=['patch'], url_path='update-status')
    def update_status(self, request, pk=None):
        referral = self.get_object()
        
        if referral.receiving_facility != request.user.facility:
            raise PermissionDenied("You can only Accept or Reject referrals sent TO your facility.")

        if referral.status != 'PENDING':
            return Response(
                {"detail": f"This referral has already been {referral.status.lower()}."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = ReferralStatusUpdateSerializer(referral, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        updated_referral = serializer.save(updated_by=request.user)

        return Response({
            "detail": f"Referral successfully {updated_referral.status.lower()}.",
            "status": updated_referral.status
        }, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Get Full Patient Medical History for a Referral",
        description=(
            "Returns the complete medical history of the referred patient — demographics, "
            "all appointments, vitals, and consultation notes. "
            "Accessible to the referring facility and, for PRIMARY referrals, also to the receiving facility."
        ),
        tags=["Patient Referrals"],
    )
    @action(detail=True, methods=['get'], url_path='patient-history')
    def patient_history(self, request, pk=None):
        referral = self.get_object()
        user_facility = request.user.facility

        is_referring = referral.referring_facility == user_facility
        is_receiving = referral.receiving_facility == user_facility

        if not is_referring and not is_receiving:
            raise PermissionDenied(
                "You can only view the medical history for referrals sent from or received by your facility."
            )

        patient = referral.patient

        # Patient profile
        profile = getattr(patient, 'patient_profile', None)
        profile_data = None
        if profile:
            profile_data = ReferralPatientProfileSummarySerializer({
                "patient_id": profile.patient_id,
                "sex": profile.sex,
                "date_of_birth": profile.date_of_birth,
                "age": profile.age,
                "age_group": profile.age_group,
                "blood_group": profile.blood_group,
                "genotype": profile.genotype,
                "lga": profile.lga,
                "ward": profile.ward,
                "allergies": profile.allergies,
                "chronic_conditions": profile.chronic_conditions,
                "insurance_status": profile.insurance_status,
                "next_of_kin_name": profile.next_of_kin_name,
                "next_of_kin_phone": profile.next_of_kin_phone,
                "next_of_kin_relationship": profile.next_of_kin_relationship,
            }).data

        # All appointments
        appointments_qs = Appointment.objects.filter(patient=patient).order_by('-appointment_date', '-appointment_time')
        appointments_data = ReferralAppointmentSummarySerializer([{
            "id": a.id,
            "appointment_id": a.appointment_id,
            "appointment_date": a.appointment_date,
            "appointment_time": a.appointment_time,
            "visit_type": a.visit_type,
            "status": a.status,
            "priority": a.priority,
            "reason_for_visit": a.reason_for_visit,
        } for a in appointments_qs], many=True).data

        # All vitals (skip blank auto-created ones that have no measurements)
        vitals_qs = Vitals.objects.filter(patient=patient).order_by('-created_at')
        vitals_data = ReferralVitalsSummarySerializer([{
            "vital_id": v.vital_id,
            "created_at": v.created_at,
            "temperature": v.temperature,
            "blood_pressure": v.blood_pressure,
            "pulse_rate": v.pulse_rate,
            "respiratory_rate": v.respiratory_rate,
            "weight_kg": v.weight_kg,
            "height_cm": v.height_cm,
            "spo2": v.spo2,
            "bmi": v.bmi,
        } for v in vitals_qs], many=True).data

        # All consultations
        consultations_qs = Consultation.objects.filter(patient=patient).order_by('-created_at')
        consultations_data = ReferralConsultationSummarySerializer([{
            "consultation_id": c.consultation_id,
            "created_at": c.created_at,
            "chief_complaint": c.chief_complaint,
            "primary_diagnosis": c.primary_diagnosis,
            "secondary_diagnosis": c.secondary_diagnosis,
            "treatment_plan": c.treatment_plan,
            "additional_notes": c.additional_notes,
        } for c in consultations_qs], many=True).data

        return Response({
            "referral_id": referral.referral_id,
            "patient": {
                "id": str(patient.id),
                "first_name": patient.first_name,
                "last_name": patient.last_name,
                "middle_name": patient.middle_name,
                "phone_number": patient.phone_number,
                "email": patient.email,
                "profile": profile_data,
            },
            "appointments": appointments_data,
            "vitals": vitals_data,
            "consultations": consultations_data,
        })


class ExternalReferralActionView(APIView):
    """
    Public endpoint. No auth required. 
    Secured by Django's cryptographic TimestampSigner.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["Patient Referrals"],
        summary="Process External Magic Link Action",
        parameters=[
            OpenApiParameter(name='token', description='The cryptographic token from the email', required=True, type=str),
        ],
        responses={
            200: inline_serializer(
                name='ExternalReferralSuccessResponse',
                fields={
                    'status': serializers.CharField(),
                    'message': serializers.CharField(),
                    'referral_id': serializers.CharField(),
                    'patient': serializers.CharField(),
                }
            ),
            400: inline_serializer(
                name='ExternalReferralErrorResponse',
                fields={
                    'error': serializers.CharField(),
                }
            ),
            404: inline_serializer(
                name='ExternalReferralNotFoundResponse',
                fields={
                    'error': serializers.CharField(),
                }
            )
        }
    )
    def get(self, request):
        token = request.query_params.get('token')
        if not token:
            return Response({"error": "Token is missing."}, status=status.HTTP_400_BAD_REQUEST)

        signer = TimestampSigner()

        try:
            payload = signer.unsign(token, max_age=604800)
            ref_id, action = payload.split(':')
            referral = Referral.objects.get(id=ref_id)

            if referral.status != 'PENDING':
                return Response(
                    {"message": f"This referral has already been processed and is currently marked as {referral.status}."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            referral.status = action
            referral.save(update_fields=['status', 'updated_at'])

            return Response({
                "status": "success",
                "message": f"Thank you! The referral has been successfully marked as {action}.",
                "referral_id": referral.referral_id,
                "patient": f"{referral.patient.first_name} {referral.patient.last_name}"
            }, status=status.HTTP_200_OK)

        except SignatureExpired:
            return Response({"error": "This link has expired. Please contact the referring facility."}, status=status.HTTP_400_BAD_REQUEST)
        except (BadSignature, ValueError):
            return Response({"error": "Invalid or tampered security token."}, status=status.HTTP_400_BAD_REQUEST)
        except Referral.DoesNotExist:
            return Response({"error": "Referral record not found in the system."}, status=status.HTTP_404_NOT_FOUND)
