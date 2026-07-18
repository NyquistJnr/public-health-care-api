from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter

from core.utils import get_validated_date_range
from core.permissions import IsClinicalStatsViewer
from appointments.models import Appointment
from consultations.models import Consultation
from laboratory.models import LabRequest
from prescriptions.models import Prescription
from referrals.models import Referral

DATE_RANGE_PARAMETERS = [
    OpenApiParameter(name='start_date', description='Start date (YYYY-MM-DD)', required=False, type=str),
    OpenApiParameter(name='end_date', description='End date (YYYY-MM-DD)', required=False, type=str),
]

def get_facility_q(request, prefix='facility'):
    user = request.user
    if user.is_superuser or user.role in ['ADMIN', 'STATE_IT_ADMIN']:
        return Q()
    if user.facility:
        return Q(**{prefix: user.facility})
    return Q(pk__isnull=True)  # Return none if user has no facility and isn't admin

@extend_schema(
    tags=["Clinical Analytics"],
    summary="Get Today's Patients Stats",
    description="Stats for waiting patients, seen patients, referrals, consultations, and lab tests.",
    parameters=DATE_RANGE_PARAMETERS,
)
class ClinicalStatsView(APIView):
    permission_classes = [IsClinicalStatsViewer]

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)

        # Base Filters
        apt_filter = Q(appointment_date__range=[start_date, end_date]) & get_facility_q(request, 'facility')
        
        waiting_status = ['SCHEDULED', 'ARRIVED', 'VITALS_DONE']
        seen_status = ['IN_CONSULTATION', 'COMPLETED']

        waiting_patients = Appointment.objects.filter(apt_filter, status__in=waiting_status).count()
        seen_patients = Appointment.objects.filter(apt_filter, status__in=seen_status).count()

        # Referrals
        ref_out_filter = Q(created_at__date__range=[start_date, end_date]) & get_facility_q(request, 'referring_facility')
        ref_in_filter = Q(created_at__date__range=[start_date, end_date]) & get_facility_q(request, 'receiving_facility')
        referred_out = Referral.objects.filter(ref_out_filter).count()
        referred_in = Referral.objects.filter(ref_in_filter).count()

        # Consultations & Lab Tests
        con_filter = Q(created_at__date__range=[start_date, end_date]) & get_facility_q(request, 'appointment__facility')
        consultations = Consultation.objects.filter(con_filter).count()

        lab_filter = Q(created_at__date__range=[start_date, end_date]) & get_facility_q(request, 'appointment__facility')
        lab_tests = LabRequest.objects.filter(lab_filter).count()

        return Response({
            "todays_patients": {
                "waiting_patients": waiting_patients,
                "seen_attended_to_patient": seen_patients,
                "referred_patients": {
                    "out": referred_out,
                    "in": referred_in,
                    "total": referred_out + referred_in
                }
            },
            "consultations": consultations,
            "lab_tests": lab_tests
        })


@extend_schema(
    tags=["Clinical Analytics"],
    summary="Get Patient Visit Trend",
    description="Bar chart data: Number of patients against dates.",
    parameters=DATE_RANGE_PARAMETERS,
)
class PatientVisitTrendView(APIView):
    permission_classes = [IsClinicalStatsViewer]

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)
        apt_filter = Q(appointment_date__range=[start_date, end_date]) & get_facility_q(request, 'facility')

        trends = (
            Appointment.objects.filter(apt_filter)
            .annotate(date=TruncDate('appointment_date'))
            .values('date')
            .annotate(count=Count('id'))
            .order_by('date')
        )

        results = [{"date": item['date'], "count": item['count']} for item in trends]
        return Response({"start_date": start_date, "end_date": end_date, "trend": results})


@extend_schema(
    tags=["Clinical Analytics"],
    summary="Get Clinical Activity Stats",
    description="Counts of Consultations, Lab tests, and Prescriptions.",
    parameters=DATE_RANGE_PARAMETERS,
)
class ClinicalActivityView(APIView):
    permission_classes = [IsClinicalStatsViewer]

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)
        
        base_filter = Q(created_at__date__range=[start_date, end_date]) & get_facility_q(request, 'appointment__facility')

        consultations = Consultation.objects.filter(base_filter).count()
        lab_tests = LabRequest.objects.filter(base_filter).count()
        prescriptions = Prescription.objects.filter(base_filter).count()

        return Response({
            "consultations": consultations,
            "lab_tests": lab_tests,
            "prescriptions": prescriptions
        })


@extend_schema(
    tags=["Clinical Analytics"],
    summary="Get Disease Overview",
    description="Array of each of the diseases and their percentages.",
    parameters=DATE_RANGE_PARAMETERS,
)
class DiseaseOverviewView(APIView):
    permission_classes = [IsClinicalStatsViewer]

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)
        
        con_filter = Q(created_at__date__range=[start_date, end_date]) & get_facility_q(request, 'appointment__facility')
        
        # We only want consultations that have a diagnosed disease
        qs = Consultation.objects.filter(con_filter, diagnosed_disease__isnull=False)
        total_diseases = qs.count()

        disease_counts = (
            qs.values('diagnosed_disease__name')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        results = []
        for item in disease_counts:
            name = item['diagnosed_disease__name']
            count = item['count']
            percentage = round((count / total_diseases) * 100, 2) if total_diseases > 0 else 0
            results.append({
                "disease": name,
                "count": count,
                "percentage": percentage
            })

        return Response({
            "total_diagnoses": total_diseases,
            "diseases": results
        })
