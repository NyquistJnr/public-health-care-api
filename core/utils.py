# core/utils.py
import re
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError


def get_validated_date_range(request, default_days=30, max_days=366):
    """
    Parses start_date/end_date query params (YYYY-MM-DD). Defaults to the last
    `default_days` days ending today. Raises ValidationError on bad format,
    start_date after end_date, or a range wider than `max_days`.
    """
    today = timezone.now().date()
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')

    try:
        end_date = timezone.datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else today
        start_date = timezone.datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else end_date - timedelta(days=default_days)
    except ValueError:
        raise ValidationError({"detail": "start_date/end_date must be in YYYY-MM-DD format."})

    if start_date > end_date:
        raise ValidationError({"detail": "start_date must not be after end_date."})
    if (end_date - start_date).days > max_days:
        raise ValidationError({"detail": f"Range cannot exceed {max_days} days."})

    return start_date, end_date


def format_last_active_label(last_active_at):
    """Buckets a datetime into 'Today' / 'Yesterday' / 'N Days' / 'Never'."""
    if not last_active_at:
        return "Never"

    delta_days = (timezone.now().date() - last_active_at.date()).days
    if delta_days <= 0:
        return "Today"
    if delta_days == 1:
        return "Yesterday"
    return f"{delta_days} Days"


def word_boundary_q(field_lookup, patterns):
    """Builds an OR'd Q using Postgres word-boundary regex (\\y) rather than icontains,
    since short acronym patterns like "ARI"/"TB"/"HIV" would otherwise false-match as a
    bare substring of unrelated names (e.g. icontains 'ARI' matches 'Malaria')."""
    q = Q()
    for pattern in patterns:
        q |= Q(**{f"{field_lookup}__iregex": rf"\y{re.escape(pattern)}\y"})
    return q


def facility_status_from_last_active(last_active_at):
    """Active: activity within 3 days. Low Activity: 4-14 days. Inactive: 15+ days or never."""
    if not last_active_at:
        return "Inactive"

    delta_days = (timezone.now().date() - last_active_at.date()).days
    if delta_days <= 3:
        return "Active"
    if delta_days <= 14:
        return "Low Activity"
    return "Inactive"
