# core/view_stats.py
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta

from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from facilities.models import Facility
from .models import FailedLoginAttempt, LoginEvent, ModuleUsageLog, UserSession
from .pagination import StandardResultsSetPagination
from .permissions import IsStateAdmin
from .serializers_stats import (
    DashboardStatsSerializer,
    FacilityUsageTableSerializer,
    FailedLoginsByFacilitySerializer,
    FailedLoginsByUserSerializer,
    FailedLoginsUnknownEmailSerializer,
    ModuleUsageStatsSerializer,
    TopActiveFacilitySerializer,
    UserActivityTrendSerializer,
)
from .utils import get_validated_date_range

DATE_RANGE_PARAMETERS = [
    OpenApiParameter(name='start_date', description='Start date (YYYY-MM-DD). Defaults to 30 days ago.', required=False, type=str),
    OpenApiParameter(name='end_date', description='End date (YYYY-MM-DD). Defaults to today.', required=False, type=str),
]


def _as_range_bounds(start_date, end_date):
    """Converts a date range into aware start-of-day / end-of-day datetimes."""
    range_start = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
    range_end = timezone.make_aware(timezone.datetime.combine(end_date, timezone.datetime.max.time()))
    return range_start, range_end


def _total_session_minutes(range_start, range_end):
    """Sums UserSession durations that overlap [range_start, range_end], clipped to those bounds."""
    sessions = UserSession.objects.filter(started_at__lte=range_end).filter(
        Q(ended_at__gte=range_start) | Q(ended_at__isnull=True, last_active_at__gte=range_start)
    ).values_list('started_at', 'last_active_at', 'ended_at')

    total_seconds = 0
    for started_at, last_active_at, ended_at in sessions:
        effective_end = ended_at or last_active_at
        clipped_start = max(started_at, range_start)
        clipped_end = min(effective_end, range_end)
        if clipped_end > clipped_start:
            total_seconds += (clipped_end - clipped_start).total_seconds()

    return int(total_seconds // 60)


@extend_schema(
    tags=["Analytics"],
    summary="Get State-Wide Dashboard Stats",
    description="KPI tile data: total active users, active facilities, total logins, and active session time.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=DashboardStatsSerializer
)
class DashboardStatsView(APIView):
    permission_classes = [IsStateAdmin]

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)
        range_start, range_end = _as_range_bounds(start_date, end_date)

        login_qs = LoginEvent.objects.filter(timestamp__date__range=[start_date, end_date])

        total_active_users = login_qs.values('user').distinct().count()
        active_facilities = login_qs.filter(facility__isnull=False).values('facility').distinct().count()
        total_facilities = Facility.objects.filter(is_active=True).count()
        total_logins = login_qs.count()

        active_sessions_minutes = _total_session_minutes(range_start, range_end)
        hours, minutes = divmod(active_sessions_minutes, 60)

        return Response({
            "start_date": start_date,
            "end_date": end_date,
            "total_active_users": total_active_users,
            "active_facilities": {"active": active_facilities, "total": total_facilities},
            "total_logins": total_logins,
            "active_sessions": f"{hours}h {minutes}m",
            "active_sessions_minutes": active_sessions_minutes,
        })


@extend_schema(
    tags=["Analytics"],
    summary="Get Daily User Activity Trend (Bar Chart)",
    description="Day-by-day breakdown of distinct active users and total logins, for the given range.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=UserActivityTrendSerializer
)
class UserActivityTrendView(APIView):
    permission_classes = [IsStateAdmin]

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)

        login_qs = LoginEvent.objects.filter(timestamp__date__range=[start_date, end_date])

        logins_by_day = {
            row['day']: row['count']
            for row in login_qs.annotate(day=TruncDate('timestamp')).values('day').annotate(count=Count('id')).order_by('day')
        }
        active_users_by_day = {
            row['day']: row['count']
            for row in login_qs.annotate(day=TruncDate('timestamp')).values('day').annotate(count=Count('user', distinct=True)).order_by('day')
        }

        results = []
        current_day = start_date
        while current_day <= end_date:
            results.append({
                "date": current_day,
                "active_users": active_users_by_day.get(current_day, 0),
                "logins": logins_by_day.get(current_day, 0),
            })
            current_day += timedelta(days=1)

        return Response({"start_date": start_date, "end_date": end_date, "results": results})


@extend_schema(
    tags=["Analytics"],
    summary="Get Module Usage Breakdown",
    description="Request counts (and share of total) for Patient Records, Patient Registry, Pharmacy, and Lab.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=ModuleUsageStatsSerializer
)
class ModuleUsageStatsView(APIView):
    permission_classes = [IsStateAdmin]

    def get(self, request):
        start_date, end_date = get_validated_date_range(request)

        counts = dict(
            ModuleUsageLog.objects.filter(timestamp__date__range=[start_date, end_date])
            .values('module').annotate(count=Count('id')).values_list('module', 'count')
        )
        total = sum(counts.values())

        results = [
            {
                "module": key,
                "label": label,
                "count": counts.get(key, 0),
                "percentage": round((counts.get(key, 0) / total) * 100, 2) if total else 0.0,
            }
            for key, label in ModuleUsageLog.MODULE_CHOICES
        ]

        return Response({"start_date": start_date, "end_date": end_date, "results": results})


@extend_schema(
    tags=["Analytics"],
    summary="Get Top Active Facilities (Paginated, by Usage %)",
    description="Facilities ranked by module-usage activity in the given range, each with its share of total system-wide usage.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=TopActiveFacilitySerializer
)
class TopActiveFacilitiesView(generics.ListAPIView):
    permission_classes = [IsStateAdmin]
    serializer_class = TopActiveFacilitySerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        start_date, end_date = get_validated_date_range(self.request)
        return Facility.objects.filter(is_active=True).annotate(
            usage_count=Count('usage_logs', filter=Q(usage_logs__timestamp__date__range=[start_date, end_date]))
        ).order_by('-usage_count')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        start_date, end_date = get_validated_date_range(self.request)
        context['total_usage'] = ModuleUsageLog.objects.filter(timestamp__date__range=[start_date, end_date]).count()
        return context


@extend_schema(
    tags=["Analytics"],
    summary="Get Facility Usage Table (Paginated)",
    description="Per-facility usage: user count, login count in range, last-active label, and Active/Low Activity/Inactive status.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=FacilityUsageTableSerializer
)
class FacilityUsageTableView(generics.ListAPIView):
    permission_classes = [IsStateAdmin]
    serializer_class = FacilityUsageTableSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        start_date, end_date = get_validated_date_range(self.request)
        return Facility.objects.filter(is_active=True).annotate(
            number_of_users=Count(
                'staff_members',
                filter=~Q(staff_members__role='PATIENT') & Q(staff_members__is_active=True),
                distinct=True
            ),
            number_of_logins=Count('login_events', filter=Q(login_events__timestamp__date__range=[start_date, end_date])),
            last_active_at=Max('staff_members__last_active'),
        ).order_by('-last_active_at')


@extend_schema(
    tags=["Analytics"],
    summary="Get Failed Login Attempts, Grouped by User (Paginated)",
    parameters=DATE_RANGE_PARAMETERS,
    responses=FailedLoginsByUserSerializer
)
class FailedLoginsByUserView(generics.ListAPIView):
    permission_classes = [IsStateAdmin]
    serializer_class = FailedLoginsByUserSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        start_date, end_date = get_validated_date_range(self.request)
        return FailedLoginAttempt.objects.filter(
            timestamp__date__range=[start_date, end_date], user__isnull=False
        ).values(
            'user', 'user__email', 'user__first_name', 'user__last_name', 'user__staff_id'
        ).annotate(count=Count('id')).order_by('-count')


@extend_schema(
    tags=["Analytics"],
    summary="Get Failed Login Attempts, Grouped by Facility (Paginated)",
    parameters=DATE_RANGE_PARAMETERS,
    responses=FailedLoginsByFacilitySerializer
)
class FailedLoginsByFacilityView(generics.ListAPIView):
    permission_classes = [IsStateAdmin]
    serializer_class = FailedLoginsByFacilitySerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        start_date, end_date = get_validated_date_range(self.request)
        return FailedLoginAttempt.objects.filter(
            timestamp__date__range=[start_date, end_date], facility__isnull=False
        ).values('facility__code', 'facility__name').annotate(count=Count('id')).order_by('-count')


@extend_schema(
    tags=["Analytics"],
    summary="Get Failed Login Attempts for Unknown Emails (Paginated)",
    description="Failed login attempts where the email did not match any account in the system.",
    parameters=DATE_RANGE_PARAMETERS,
    responses=FailedLoginsUnknownEmailSerializer
)
class FailedLoginsUnknownEmailsView(generics.ListAPIView):
    permission_classes = [IsStateAdmin]
    serializer_class = FailedLoginsUnknownEmailSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        start_date, end_date = get_validated_date_range(self.request)
        return FailedLoginAttempt.objects.filter(
            timestamp__date__range=[start_date, end_date], user__isnull=True
        ).values('attempted_email').annotate(count=Count('id')).order_by('-count')
