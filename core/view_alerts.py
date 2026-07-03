# core/view_alerts.py
from datetime import timedelta

from django.db.models import Count, Max
from django.utils import timezone
from drf_spectacular.utils import extend_schema

from rest_framework import generics

from consultations.models import Consultation
from facilities.models import Facility
from registry.models import SystemThreshold
from .models import ErrorLog, FailedLoginAttempt, LoginEvent
from .pagination import StandardResultsSetPagination
from .permissions import IsStateAdmin
from .serializers_alerts import AlertItemSerializer

DISEASE_WINDOW_DAYS = 30
SECURITY_WINDOW_HOURS = 24
MIN_DIAGNOSES_FOR_COMPLIANCE_CHECK = 5


def _disease_critical_alerts(now):
    since = now - timedelta(days=DISEASE_WINDOW_DAYS)
    consultations = Consultation.objects.filter(
        diagnosed_disease__severity='CRITICAL',
        created_at__gte=since,
    ).select_related('diagnosed_disease', 'doctor__facility')

    alerts = []
    for c in consultations:
        facility = c.doctor.facility if c.doctor else None
        alerts.append({
            "type": "DISEASE_CRITICAL_DIAGNOSIS",
            "severity": "CRITICAL",
            "title": f"Critical diagnosis: {c.diagnosed_disease.name}",
            "message": (
                f"A patient was diagnosed with {c.diagnosed_disease.name} "
                f"({c.diagnosed_disease.get_severity_display()}) at "
                f"{facility.name if facility else 'an unassigned facility'}."
            ),
            "facility_id": facility.code if facility else None,
            "facility_name": facility.name if facility else None,
            "disease": c.diagnosed_disease.name,
            "detected_at": c.created_at,
            "metric_value": 1,
            "threshold_value": None,
        })
    return alerts


def _disease_threshold_alerts(now, threshold_percent):
    since = now - timedelta(days=DISEASE_WINDOW_DAYS)
    base_qs = Consultation.objects.filter(
        diagnosed_disease__isnull=False, doctor__facility__isnull=False, created_at__gte=since
    )

    totals = {
        row['doctor__facility']: row['total']
        for row in base_qs.values('doctor__facility').annotate(total=Count('id'))
    }

    per_disease = base_qs.values(
        'doctor__facility', 'doctor__facility__code', 'doctor__facility__name', 'diagnosed_disease__name'
    ).annotate(disease_count=Count('id'))

    alerts = []
    for row in per_disease:
        total = totals.get(row['doctor__facility'], 0)
        if total < MIN_DIAGNOSES_FOR_COMPLIANCE_CHECK:
            continue

        percentage = round((row['disease_count'] / total) * 100, 2)
        if percentage >= threshold_percent:
            alerts.append({
                "type": "DISEASE_THRESHOLD_BREACH",
                "severity": "HIGH",
                "title": f"{row['diagnosed_disease__name']} exceeds {threshold_percent}% of diagnoses",
                "message": (
                    f"{row['diagnosed_disease__name']} accounts for {percentage}% of all diagnoses at "
                    f"{row['doctor__facility__name']} in the last {DISEASE_WINDOW_DAYS} days."
                ),
                "facility_id": row['doctor__facility__code'],
                "facility_name": row['doctor__facility__name'],
                "disease": row['diagnosed_disease__name'],
                "detected_at": now,
                "metric_value": percentage,
                "threshold_value": threshold_percent,
            })
    return alerts


def _failed_login_alerts(now, threshold):
    since = now - timedelta(hours=SECURITY_WINDOW_HOURS)
    alerts = []

    by_user = FailedLoginAttempt.objects.filter(timestamp__gte=since, user__isnull=False).values(
        'user__email', 'user__first_name', 'user__last_name', 'user__facility__code', 'user__facility__name'
    ).annotate(count=Count('id')).filter(count__gte=threshold)

    for row in by_user:
        name = f"{row['user__first_name']} {row['user__last_name']}".strip() or row['user__email']
        alerts.append({
            "type": "FAILED_LOGIN_SPIKE",
            "severity": "HIGH",
            "title": f"{row['count']} failed logins for {row['user__email']}",
            "message": f"{name} had {row['count']} failed login attempts in the last {SECURITY_WINDOW_HOURS} hours.",
            "facility_id": row['user__facility__code'],
            "facility_name": row['user__facility__name'],
            "disease": None,
            "detected_at": now,
            "metric_value": row['count'],
            "threshold_value": threshold,
        })

    by_facility = FailedLoginAttempt.objects.filter(timestamp__gte=since, facility__isnull=False).values(
        'facility__code', 'facility__name'
    ).annotate(count=Count('id')).filter(count__gte=threshold)

    for row in by_facility:
        alerts.append({
            "type": "FAILED_LOGIN_SPIKE",
            "severity": "HIGH",
            "title": f"{row['count']} failed logins at {row['facility__name']}",
            "message": (
                f"{row['facility__name']} recorded {row['count']} failed login attempts "
                f"in the last {SECURITY_WINDOW_HOURS} hours."
            ),
            "facility_id": row['facility__code'],
            "facility_name": row['facility__name'],
            "disease": None,
            "detected_at": now,
            "metric_value": row['count'],
            "threshold_value": threshold,
        })

    return alerts


def _system_error_alerts(now, threshold):
    since = now - timedelta(hours=SECURITY_WINDOW_HOURS)
    count = ErrorLog.objects.filter(timestamp__gte=since).count()

    if count < threshold:
        return []

    return [{
        "type": "SYSTEM_ERROR_SPIKE",
        "severity": "CRITICAL",
        "title": f"{count} system errors in the last {SECURITY_WINDOW_HOURS} hours",
        "message": f"The system logged {count} server errors in the last {SECURITY_WINDOW_HOURS} hours, above the threshold of {threshold}.",
        "facility_id": None,
        "facility_name": None,
        "disease": None,
        "detected_at": now,
        "metric_value": count,
        "threshold_value": threshold,
    }]


def _inactive_facility_alerts(now, threshold_days):
    facilities = Facility.objects.filter(is_active=True).annotate(last_active_at=Max('staff_members__last_active'))

    alerts = []
    for facility in facilities:
        if facility.last_active_at is None:
            days_inactive = None
            qualifies = True
        else:
            days_inactive = (now.date() - facility.last_active_at.date()).days
            qualifies = days_inactive >= threshold_days

        if not qualifies:
            continue

        alerts.append({
            "type": "FACILITY_INACTIVE",
            "severity": "MEDIUM",
            "title": f"{facility.name} inactive",
            "message": (
                f"{facility.name} has had no recorded staff activity for {days_inactive} days."
                if days_inactive is not None else f"{facility.name} has no recorded staff activity yet."
            ),
            "facility_id": facility.code,
            "facility_name": facility.name,
            "disease": None,
            "detected_at": now,
            "metric_value": days_inactive if days_inactive is not None else -1,
            "threshold_value": threshold_days,
        })
    return alerts


def _high_usage_alert(now, threshold):
    today_count = LoginEvent.objects.filter(timestamp__date=now.date()).values('user').distinct().count()

    if today_count < threshold:
        return []

    return [{
        "type": "HIGH_SYSTEM_USAGE",
        "severity": "MEDIUM",
        "title": f"{today_count} active users today",
        "message": f"{today_count} distinct users have logged in today, above the threshold of {threshold}.",
        "facility_id": None,
        "facility_name": None,
        "disease": None,
        "detected_at": now,
        "metric_value": today_count,
        "threshold_value": threshold,
    }]


@extend_schema(
    tags=["Alerts"],
    summary="Get Active System Alerts (Paginated)",
    description=(
        "Unified feed computed on every request, evaluated against the global SystemThreshold config: "
        "critical-disease diagnoses (trailing 30 days), disease compliance breaches "
        "(share of a facility's diagnoses, trailing 30 days, min 5 diagnoses sampled), "
        "failed-login spikes (trailing 24 hours, by user and by facility), system error spikes "
        "(trailing 24 hours), inactive facilities (current recency vs threshold), and high system "
        "usage (today's distinct active users vs threshold)."
    ),
    responses=AlertItemSerializer
)
class ActiveAlertsView(generics.ListAPIView):
    permission_classes = [IsStateAdmin]
    serializer_class = AlertItemSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        now = timezone.now()
        thresholds = SystemThreshold.get_solo()

        alerts = []
        alerts += _disease_critical_alerts(now)
        alerts += _disease_threshold_alerts(now, thresholds.disease_compliance_threshold_percent)
        alerts += _failed_login_alerts(now, thresholds.failed_login_attempts_threshold)
        alerts += _system_error_alerts(now, thresholds.system_error_threshold)
        alerts += _inactive_facility_alerts(now, thresholds.inactive_facility_threshold_days)
        alerts += _high_usage_alert(now, thresholds.high_usage_threshold_users)

        alerts.sort(key=lambda a: a['detected_at'], reverse=True)
        return alerts
