from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import datetime, timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.exceptions import ValidationError

from core.models import User, PatientProfile
from appointments.models import Appointment
from consultations.models import Consultation
from laboratory.models import LabRequest, LabTest
from prescriptions.models import Prescription
from referrals.models import Referral
from maternal_care.models import MaternalCareEpisode, ANCVisit, PNCVisit
from nurse_chew.models import HealthPromotion
from core.pagination import StandardResultsSetPagination

def get_facility_q(request, prefix='facility'):
    user = request.user
    if user.is_superuser or user.role in ['ADMIN', 'STATE_IT_ADMIN']:
        return Q()
    if user.facility:
        return Q(**{prefix: user.facility})
    return Q(pk__isnull=True)

def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        raise ValidationError("Invalid date format. Use YYYY-MM-DD.")

@extend_schema(
    tags=["Reports"],
    summary="Daily Clinical Activity Report",
    description="Returns paginated daily breakdown of patient visits, diagnosis, lab tests, prescriptions, and appointments.",
    parameters=[
        OpenApiParameter(name='start_date', description='Start date (YYYY-MM-DD)', required=True, type=str),
        OpenApiParameter(name='end_date', description='End date (YYYY-MM-DD)', required=True, type=str),
    ]
)
class DailyActivityReportView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get(self, request):
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        if not start_date_str or not end_date_str:
            raise ValidationError({"detail": "start_date and end_date are required."})

        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str)

        if start_date > end_date:
            raise ValidationError({"detail": "start_date cannot be after end_date."})

        # Generate list of dates
        delta = end_date - start_date
        date_list = [start_date + timedelta(days=i) for i in range(delta.days + 1)]
        date_list.sort(reverse=True) # Most recent first

        page = self.paginate_queryset(date_list)
        if page is not None:
            dates_to_query = page
        else:
            dates_to_query = date_list

        if not dates_to_query:
            return self.get_paginated_response([])

        q_start = dates_to_query[-1]
        q_end = dates_to_query[0]

        # Base Filters
        apt_fac = get_facility_q(request, 'facility')
        con_fac = get_facility_q(request, 'appointment__facility')

        # Aggregate counts for the date range
        def get_daily_counts(qs, date_field):
            data = qs.annotate(date=TruncDate(date_field)).values('date').annotate(count=Count('id'))
            return {item['date']: item['count'] for item in data if item['date']}

        appointments = get_daily_counts(
            Appointment.objects.filter(apt_fac, appointment_date__range=[q_start, q_end]),
            'appointment_date'
        )

        # "Patient Visits" might be appointments that are actually arrived/seen
        visits = get_daily_counts(
            Appointment.objects.filter(apt_fac, appointment_date__range=[q_start, q_end], status__in=['ARRIVED', 'VITALS_DONE', 'IN_CONSULTATION', 'COMPLETED']),
            'appointment_date'
        )

        diagnoses = get_daily_counts(
            Consultation.objects.filter(con_fac, created_at__date__range=[q_start, q_end], diagnosed_disease__isnull=False),
            'created_at'
        )

        lab_tests = get_daily_counts(
            LabRequest.objects.filter(con_fac, created_at__date__range=[q_start, q_end]),
            'created_at'
        )

        prescriptions = get_daily_counts(
            Prescription.objects.filter(con_fac, created_at__date__range=[q_start, q_end]),
            'created_at'
        )

        results = []
        for d in dates_to_query:
            results.append({
                "date": d,
                "patient_visits": visits.get(d, 0),
                "diagnosis": diagnoses.get(d, 0),
                "lab_tests": lab_tests.get(d, 0),
                "prescriptions": prescriptions.get(d, 0),
                "appointments": appointments.get(d, 0)
            })

        if page is not None:
            return self.get_paginated_response(results)
        return Response(results)


@extend_schema(
    tags=["Reports"],
    summary="Comprehensive Medical Modules Report",
    description="Fetches aggregated summary for requested modules or all modules if not specified. Pass 'modules' as comma-separated list.",
    parameters=[
        OpenApiParameter(name='start_date', description='Start date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='End date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='modules', description='Comma separated list of modules (e.g. patients,appointments)', required=False, type=str),
    ]
)
class ComprehensiveModuleReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        modules_param = request.query_params.get('modules')

        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str) if end_date_str else start_date

        if start_date and end_date and start_date > end_date:
            raise ValidationError({"detail": "start_date cannot be after end_date."})

        requested_modules = [m.strip().lower() for m in modules_param.split(',')] if modules_param else []

        def is_requested(module_name):
            return not requested_modules or module_name.lower() in requested_modules

        response_data = {}
        
        # Scopes
        fac_q = get_facility_q(request, 'facility')
        apt_fac_q = get_facility_q(request, 'appointment__facility')
        out_ref_q = get_facility_q(request, 'referring_facility')
        ep_fac_q = get_facility_q(request, 'patient__facility')
        visit_fac_q = get_facility_q(request, 'episode__patient__facility')

        def build_date_q(field_name):
            if start_date and end_date:
                if field_name == 'appointment_date':
                    return Q(**{f"{field_name}__range": [start_date, end_date]})
                return Q(**{f"{field_name}__date__range": [start_date, end_date]})
            return Q()

        def get_count_and_completed(qs, completed_filter, date_field='created_at'):
            base_qs = qs.filter(build_date_q(date_field))
            count = base_qs.count()
            completed = base_qs.filter(completed_filter).count() if completed_filter is not None else count
            return count, completed

        if is_requested('patients'):
            c, comp = get_count_and_completed(User.objects.filter(fac_q, role='PATIENT'), Q(is_active=True), 'created_at')
            response_data['patients'] = {
                "count": c,
                "completed": comp,
                "summary": "Great job! Keep ensuring patient details are accurately captured." if c > 0 else "No new patients registered for this period."
            }

        if is_requested('appointments'):
            c, comp = get_count_and_completed(Appointment.objects.filter(fac_q), Q(status='COMPLETED'), 'appointment_date')
            response_data['appointments'] = {
                "count": c,
                "completed": comp,
                "summary": "Consistent appointments show a healthy patient engagement." if c > 0 else "No appointments scheduled."
            }

        if is_requested('ancs'):
            c, comp = get_count_and_completed(ANCVisit.objects.filter(visit_fac_q), Q(appointment__status='COMPLETED'), 'created_at')
            response_data['ancs'] = {
                "count": c,
                "completed": comp,
                "summary": f"{c} ANC visits recorded. Proper antenatal care is key for safe deliveries!"
            }

        if is_requested('pncs'):
            c, comp = get_count_and_completed(PNCVisit.objects.filter(visit_fac_q), Q(appointment__status='COMPLETED'), 'created_at')
            response_data['pncs'] = {
                "count": c,
                "completed": comp,
                "summary": f"{c} PNC visits. Postnatal tracking helps ensure mother and child are thriving."
            }

        if is_requested('delivery'):
            patient_fac_q = get_facility_q(request, 'user__facility')
            c, comp = get_count_and_completed(PatientProfile.objects.filter(patient_fac_q, birth_episode__isnull=False), None, 'created_at')
            response_data['delivery'] = {
                "count": c,
                "completed": comp,
                "summary": f"Incredible! {c} successful deliveries managed safely." if c > 0 else "No deliveries recorded."
            }

        if is_requested('lab tests'):
            c, comp = get_count_and_completed(LabRequest.objects.filter(apt_fac_q), Q(status='COMPLETED'), 'created_at')
            response_data['lab tests'] = {
                "count": c,
                "completed": comp,
                "summary": f"{c} Lab tests requested for diagnostics."
            }

        if is_requested('lab results'):
            qs = LabTest.objects.filter(lab_request__appointment__facility=request.user.facility if getattr(request.user, 'facility', None) else None) if getattr(request.user, 'facility', None) else LabTest.objects.all()
            c, comp = get_count_and_completed(qs, Q(test_status='RESULT_READY'), 'result_date')
            response_data['lab results'] = {
                "count": c,
                "completed": comp,
                "summary": f"{comp} Lab results effectively pushed to patients."
            }

        if is_requested('prescriptions'):
            c, comp = get_count_and_completed(Prescription.objects.filter(apt_fac_q), Q(status='DISPENSED'), 'created_at')
            response_data['prescriptions'] = {
                "count": c,
                "completed": comp,
                "summary": f"{comp} Prescriptions completely dispensed out of {c}."
            }

        if is_requested('referrals'):
            c, comp = get_count_and_completed(Referral.objects.filter(out_ref_q), Q(status='COMPLETED'), 'created_at')
            response_data['referrals'] = {
                "count": c,
                "completed": comp,
                "summary": f"{c} Referrals processed, extending patient care networks."
            }

        if is_requested('health promotions'):
            c, comp = get_count_and_completed(HealthPromotion.objects.filter(Q(assigned_to=request.user) | Q(created_by=request.user) | Q()), Q(status='COMPLETED'), 'start_date')
            response_data['health promotions'] = {
                "count": c,
                "completed": comp,
                "summary": f"{c} Health Promotion drives active."
            }

        if is_requested('maternal care'):
            c, comp = get_count_and_completed(MaternalCareEpisode.objects.filter(ep_fac_q), Q(status='CLOSED') | Q(status='DELIVERED'), 'created_at')
            response_data['maternal care'] = {
                "count": c,
                "completed": comp,
                "summary": f"{c} Maternal Care episodes managed."
            }

        return Response({
            "period": {
                "start_date": start_date,
                "end_date": end_date if end_date else start_date if start_date else "All Time"
            },
            "reports": response_data
        })


@extend_schema(
    tags=["Reports"],
    summary="Medical Modules Completion Percentage",
    description="Returns a list of all medical modules with their total count, completed count, and completion percentage.",
    parameters=[
        OpenApiParameter(name='start_date', description='Start date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='End date (YYYY-MM-DD)', required=False, type=str),
    ]
)
class ModuleCompletionPercentageReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str) if end_date_str else start_date

        if start_date and end_date and start_date > end_date:
            raise ValidationError({"detail": "start_date cannot be after end_date."})

        fac_q = get_facility_q(request, 'facility')
        apt_fac_q = get_facility_q(request, 'appointment__facility')
        out_ref_q = get_facility_q(request, 'referring_facility')
        ep_fac_q = get_facility_q(request, 'patient__facility')
        visit_fac_q = get_facility_q(request, 'episode__patient__facility')

        def build_date_q(field_name):
            if start_date and end_date:
                if field_name == 'appointment_date':
                    return Q(**{f"{field_name}__range": [start_date, end_date]})
                return Q(**{f"{field_name}__date__range": [start_date, end_date]})
            return Q()

        def get_count_and_completed(qs, completed_filter, date_field='created_at'):
            base_qs = qs.filter(build_date_q(date_field))
            count = base_qs.count()
            completed = base_qs.filter(completed_filter).count() if completed_filter is not None else count
            percentage = round((completed / count * 100), 2) if count > 0 else 0.0
            return count, completed, percentage

        modules_data = []

        def append_module(name, qs, completed_filter, date_field='created_at'):
            c, comp, pct = get_count_and_completed(qs, completed_filter, date_field)
            modules_data.append({
                "module_name": name,
                "total_count": c,
                "completed_count": comp,
                "completion_percentage": pct
            })

        append_module('Patients', User.objects.filter(fac_q, role='PATIENT'), Q(is_active=True))
        append_module('Appointments', Appointment.objects.filter(fac_q), Q(status='COMPLETED'), 'appointment_date')
        append_module('ANCs', ANCVisit.objects.filter(visit_fac_q), Q(appointment__status='COMPLETED'))
        append_module('PNCs', PNCVisit.objects.filter(visit_fac_q), Q(appointment__status='COMPLETED'))
        patient_fac_q = get_facility_q(request, 'user__facility')
        append_module('Delivery', PatientProfile.objects.filter(patient_fac_q, birth_episode__isnull=False), None)
        append_module('Lab Tests', LabRequest.objects.filter(apt_fac_q), Q(status='COMPLETED'))
        
        lab_results_qs = LabTest.objects.filter(lab_request__appointment__facility=request.user.facility if getattr(request.user, 'facility', None) else None) if getattr(request.user, 'facility', None) else LabTest.objects.all()
        append_module('Lab Results', lab_results_qs, Q(test_status='RESULT_READY'), 'result_date')
        
        append_module('Prescriptions', Prescription.objects.filter(apt_fac_q), Q(status='DISPENSED'))
        append_module('Referrals', Referral.objects.filter(out_ref_q), Q(status='COMPLETED'))
        append_module('Health Promotions', HealthPromotion.objects.filter(Q(assigned_to=request.user) | Q(created_by=request.user) | Q()), Q(status='COMPLETED'), 'start_date')
        append_module('Maternal Care', MaternalCareEpisode.objects.filter(ep_fac_q), Q(status='CLOSED') | Q(status='DELIVERED'))

        return Response({
            "period": {
                "start_date": start_date,
                "end_date": end_date if end_date else start_date if start_date else "All Time"
            },
            "modules": modules_data
        })
