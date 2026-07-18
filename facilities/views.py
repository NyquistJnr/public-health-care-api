# facilities/views.py
from datetime import timedelta
from rest_framework import viewsets
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db.models import Q, Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework import status
from django.db import connection

from core.models import User, UserSession, LoginEvent, FailedLoginAttempt, ErrorLog
from core.permissions import IsStateAdmin, IsFacilityITAdmin
from appointments.models import Appointment
from .models import Facility
from .serializers import (
    FacilitySerializer, StateFacilityStatsSerializer, PatientActivityChartSerializer,
    FacilityITAdminStatsSerializer, FacilityITAdminSystemStatusSerializer,
    FacilityITAdminUserActivitySerializer, FacilityITAdminSystemAlertsSerializer
)
from core.serializers import StatusUpdateSerializer, EmptyStatsSerializer


@extend_schema(tags=["Facility Management"])
class FacilityViewSet(viewsets.ModelViewSet):
    queryset = Facility.objects.all().order_by('-created_at')
    serializer_class = FacilitySerializer
    http_method_names = ['get', 'post', 'patch', 'delete'] 

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        instance.delete(deleted_by=self.request.user)

    @extend_schema(
        summary="List & Filter Facilities",
        parameters=[
            OpenApiParameter(name='is_active', description='Filter by active status (true/false)', required=False, type=str),
            OpenApiParameter(name='search', description='Search by facility name, code, or email', required=False, type=str),
            OpenApiParameter(name='state', description='Filter by state name', required=False, type=str),
            OpenApiParameter(name='lga', description='Filter by LGA', required=False, type=str),
            OpenApiParameter(name='ward', description='Filter by Ward', required=False, type=str)
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        
        is_active_param = self.request.query_params.get('is_active')
        search = self.request.query_params.get('search')
        state = self.request.query_params.get('state')
        lga = self.request.query_params.get('lga')
        ward = self.request.query_params.get('ward')

        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ['true', '1', 't', 'y', 'yes']
            qs = qs.filter(is_active=is_active_bool)

        if state:
            current_state = connection.tenant.name if hasattr(connection, 'tenant') else ""
            if state.lower() != current_state.lower():
                return qs.none()

        if lga:
            qs = qs.filter(lga__icontains=lga)
        if ward:
            qs = qs.filter(ward__icontains=ward)

        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search) |
                Q(manager_email__icontains=search) |
                Q(lga__icontains=search)
            )
            
        qs = qs.annotate(
            annotated_staff_count=Count(
                'staff_members', 
                filter=~Q(staff_members__role='PATIENT') & Q(staff_members__is_active=True), 
                distinct=True
            ),
            annotated_patient_count=Count(
                'staff_members', 
                filter=Q(staff_members__role='PATIENT') & Q(staff_members__is_active=True), 
                distinct=True
            ),
            annotated_department_count=Count(
                'departments', 
                filter=Q(departments__is_active=True), 
                distinct=True
            )
        )
            
        return qs

@extend_schema(tags=["Facility Management"], summary="Suspend or Activate an Entire Facility", request=StatusUpdateSerializer)
class FacilityStatusToggleView(APIView):
    # permission_classes = [HasRequiredPermission]
    serializer_class = StatusUpdateSerializer

    def patch(self, request, facility_id):
        serializer = StatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            facility = Facility.objects.get(id=facility_id)
            is_active = serializer.validated_data['is_active']
            facility.is_active = is_active
            facility.suspended_at = None if is_active else timezone.now()
            
            facility.save(update_fields=['is_active', 'suspended_at', 'updated_at'])

            status_text = "activated" if facility.is_active else "suspended"
            return Response({"detail": f"Facility '{facility.name}' has been {status_text}. Staff login access has been updated."})

        except Facility.DoesNotExist:
            return Response({"detail": "Facility not found."}, status=status.HTTP_404_NOT_FOUND)

@extend_schema(
    tags=["Facility Management"],
    summary="Get State-Wide Facility Statistics (State Admin Only)",
    parameters=[
        OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
    ],
    responses=StateFacilityStatsSerializer
)
class StateFacilityStatsView(APIView):
    permission_classes = [IsStateAdmin]
    serializer_class = StateFacilityStatsSerializer

    def get(self, request):
        facility_qs = Facility.objects.all()
        patient_qs = User.objects.filter(role='PATIENT')

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if start_date:
            facility_qs = facility_qs.filter(created_at__gte=start_date)
            patient_qs = patient_qs.filter(created_at__gte=start_date)
        if end_date:
            facility_qs = facility_qs.filter(created_at__lte=end_date)
            patient_qs = patient_qs.filter(created_at__lte=end_date)

        return Response({
            "total_facilities": facility_qs.count(),
            "active_facilities": facility_qs.filter(is_active=True).count(),
            "suspended_facilities": facility_qs.filter(is_active=False).count(),
            "total_registered_patients": patient_qs.count()
        })


@extend_schema(
    tags=["Facility Management"],
    summary="Get Daily Patient Registration vs Appointment Activity (State-Wide)",
    description=(
        "Returns a day-by-day breakdown of patients registered vs distinct patients who had an "
        "appointment booked, for the given range - intended for a grouped bar chart. Defaults to "
        "the last 30 days if no range is given. Range is capped at 366 days."
    ),
    parameters=[
        OpenApiParameter(name='start_date', description='Start date (YYYY-MM-DD). Defaults to 30 days ago.', required=False, type=str),
        OpenApiParameter(name='end_date', description='End date (YYYY-MM-DD). Defaults to today.', required=False, type=str),
    ],
    responses=PatientActivityChartSerializer
)
class PatientActivityChartView(APIView):
    def get(self, request):
        today = timezone.now().date()
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        try:
            end_date = timezone.datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else today
            start_date = timezone.datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else end_date - timedelta(days=30)
        except ValueError:
            raise ValidationError({"detail": "start_date/end_date must be in YYYY-MM-DD format."})

        if start_date > end_date:
            raise ValidationError({"detail": "start_date must not be after end_date."})
        if (end_date - start_date).days > 366:
            raise ValidationError({"detail": "Range cannot exceed 366 days."})

        registered_by_day = {
            row['day']: row['count']
            for row in User.objects.filter(
                role='PATIENT', created_at__date__range=[start_date, end_date]
            ).annotate(day=TruncDate('created_at')).values('day').annotate(count=Count('id')).order_by('day')
        }

        appointments_by_day = {
            row['day']: row['count']
            for row in Appointment.objects.filter(
                created_at__date__range=[start_date, end_date]
            ).annotate(day=TruncDate('created_at')).values('day').annotate(count=Count('patient', distinct=True)).order_by('day')
        }

        results = []
        current_day = start_date
        while current_day <= end_date:
            results.append({
                "date": current_day,
                "registered": registered_by_day.get(current_day, 0),
                "appointments": appointments_by_day.get(current_day, 0)
            })
            current_day += timedelta(days=1)

        return Response({
            "start_date": start_date,
            "end_date": end_date,
            "results": results
        })

@extend_schema(
    tags=["Facility IT Admin"],
    summary="Get IT Admin Dashboard Stats",
    parameters=[
        OpenApiParameter(name='start_date', description='Start date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='End date (YYYY-MM-DD)', required=False, type=str),
    ],
    responses=FacilityITAdminStatsSerializer
)
class FacilityITAdminStatsView(APIView):
    permission_classes = [IsFacilityITAdmin]

    def get(self, request):
        facility = request.user.facility
        if not facility:
            return Response({"detail": "User has no assigned facility."}, status=status.HTTP_400_BAD_REQUEST)
            
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        users_qs = User.objects.filter(facility=facility)
        
        if start_date:
            users_qs = users_qs.filter(created_at__gte=start_date)
        if end_date:
            users_qs = users_qs.filter(created_at__lte=end_date)
            
        total_users = users_qs.count()

        return Response({
            "total_users": total_users,
            "system_alert_count": 3,  # Mocked as per plan
            "system_uptime": "99.9%"  # Mocked as per plan
        })


@extend_schema(
    tags=["Facility IT Admin"],
    summary="Get System Status",
    responses=FacilityITAdminSystemStatusSerializer
)
class FacilityITAdminSystemStatusView(APIView):
    permission_classes = [IsFacilityITAdmin]

    def get(self, request):
        # We count error logs for the last 24 hours as a proxy for error alerts
        yesterday = timezone.now() - timedelta(days=1)
        error_count = ErrorLog.objects.filter(timestamp__gte=yesterday).count()

        return Response({
            "server_health": {"status": "Online", "percentage": "99.9"},
            "database_status": {"status": "Connected", "percentage": "100.0"},
            "error_alerts": {"count": str(error_count), "percentage": "2.1"},
            "system_uptime": {"uptime": "15D 10H 30M", "percentage": "99.9"}
        })


@extend_schema(
    tags=["Facility IT Admin"],
    summary="Get Real-time User Activity",
    parameters=[
        OpenApiParameter(name='start_date', description='Start date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='End date (YYYY-MM-DD)', required=False, type=str),
    ],
    responses=FacilityITAdminUserActivitySerializer
)
class FacilityITAdminUserActivityView(APIView):
    permission_classes = [IsFacilityITAdmin]

    def get(self, request):
        facility = request.user.facility
        if not facility:
            return Response({"detail": "User has no assigned facility."}, status=status.HTTP_400_BAD_REQUEST)

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        # Active users (open sessions)
        sessions_qs = UserSession.objects.filter(facility=facility, ended_at__isnull=True)
        
        # Login events
        logins_qs = LoginEvent.objects.filter(facility=facility)
        failed_qs = FailedLoginAttempt.objects.filter(facility=facility)

        if start_date:
            sessions_qs = sessions_qs.filter(started_at__gte=start_date)
            logins_qs = logins_qs.filter(timestamp__gte=start_date)
            failed_qs = failed_qs.filter(timestamp__gte=start_date)
        if end_date:
            sessions_qs = sessions_qs.filter(started_at__lte=end_date)
            logins_qs = logins_qs.filter(timestamp__lte=end_date)
            failed_qs = failed_qs.filter(timestamp__lte=end_date)

        failed_count = failed_qs.count()
        login_attempts = logins_qs.count() + failed_count

        return Response({
            "active_users": sessions_qs.count(),
            "login_attempts": login_attempts,
            "failed_logins": failed_count
        })


@extend_schema(
    tags=["Facility IT Admin"],
    summary="Get System Alerts",
    responses=FacilityITAdminSystemAlertsSerializer
)
class FacilityITAdminSystemAlertsView(APIView):
    permission_classes = [IsFacilityITAdmin]

    def get(self, request):
        facility = request.user.facility
        if not facility:
            return Response({"detail": "User has no assigned facility."}, status=status.HTTP_400_BAD_REQUEST)

        alerts = []
        
        # Check for multiple failed login attempts from same IP in last 24h
        yesterday = timezone.now() - timedelta(days=1)
        suspicious_ips = FailedLoginAttempt.objects.filter(
            facility=facility, 
            timestamp__gte=yesterday
        ).values('ip_address').annotate(count=Count('id')).filter(count__gte=3)

        for item in suspicious_ips:
            ip = item['ip_address']
            if ip:
                alerts.append({
                    "title": "Multiple Failed Login Attempts",
                    "description": f"Repeated failed logins from IP {ip} detected."
                })

        # Mocked hardware alerts as per plan
        alerts.append({
            "title": "High Memory Usage",
            "description": "Application server memory at 82% capacity"
        })
        alerts.append({
            "title": "Database Sync Delay",
            "description": "Data synchronization with backup server delayed by 30 minutes"
        })

        return Response({
            "alerts": alerts
        })


@extend_schema(
    tags=["Facility IT Admin"],
    summary="Get Current Facility Information",
    responses=FacilitySerializer
)
class FacilityITAdminInfoView(APIView):
    permission_classes = [IsFacilityITAdmin]

    def get(self, request):
        facility = request.user.facility
        if not facility:
            return Response({"detail": "User has no assigned facility."}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = FacilitySerializer(facility)
        return Response(serializer.data)

