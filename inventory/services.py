# inventory/services.py
from datetime import timedelta, date
from typing import Optional
from django.db.models import Q, Sum, F, Case, When, FloatField
from django.db.models.functions import Coalesce
from django.utils import timezone


def annotate_stock_levels(queryset):
    """
    Annotates an InventoryItem queryset with `annotated_total_stock`,
    `annotated_initial_stock`, and `calculated_threshold`, computed from
    active, non-expired batches. Used to determine low-stock/out-of-stock items.
    """
    today = timezone.now().date()
    active_batches_filter = Q(batches__is_active=True) & (
        Q(batches__expiry_date__gte=today) | Q(batches__expiry_date__isnull=True)
    )
    return queryset.annotate(
        annotated_total_stock=Coalesce(
            Sum('batches__remaining_quantity', filter=active_batches_filter), 0
        ),
        annotated_initial_stock=Coalesce(
            Sum('batches__initial_quantity', filter=active_batches_filter), 0
        )
    ).annotate(
        calculated_threshold=Case(
            When(
                threshold_type='PERCENTAGE',
                then=(F('annotated_initial_stock') * F('global_threshold')) / 100.0
            ),
            default=F('global_threshold'),
            output_field=FloatField()
        )
    )


class InsufficientStockError(Exception):
    def __init__(self, requested, available):
        self.requested = requested
        self.available = available
        super().__init__(f"Insufficient stock. Requested: {requested}. Available: {available}.")


def dispense_fifo_stock(item, quantity, performed_by):
    """
    Deducts `quantity` units of `item` from its active, non-expired batches,
    oldest-expiry-first, recording an InventoryTransaction per batch touched.
    Raises InsufficientStockError if total available stock is insufficient.
    """
    from .models import ItemBatch, InventoryTransaction

    today = timezone.now().date()
    active_batches = ItemBatch.objects.filter(
        item=item, is_active=True, remaining_quantity__gt=0
    ).filter(
        Q(expiry_date__gte=today) | Q(expiry_date__isnull=True)
    ).select_for_update().order_by('expiry_date')

    total_available = sum(batch.remaining_quantity for batch in active_batches)
    if quantity > total_available:
        raise InsufficientStockError(quantity, total_available)

    remaining_to_deduct = quantity
    for batch in active_batches:
        if remaining_to_deduct <= 0:
            break
        deducted = min(batch.remaining_quantity, remaining_to_deduct)
        batch.remaining_quantity -= deducted
        InventoryTransaction.objects.create(
            batch=batch, transaction_type='DISPENSE', quantity=-deducted, performed_by=performed_by
        )
        batch.save(update_fields=['remaining_quantity', 'updated_at'])
        remaining_to_deduct -= deducted


class ScheduleEngine:
    @staticmethod
    def calculate_next_due_date(schedule_rules: dict, previous_doses_count: int, last_dose_date: date) -> Optional[date]:
        """
        Calculates the next due date based on the item's custom JSON rules and the patient's history.
        """
        if not schedule_rules or not last_dose_date:
            return None

        rule_type = schedule_rules.get("type")

        if rule_type == "ONCE":
            return None

        elif rule_type == "RECURRING":
            interval = schedule_rules.get("interval_days", 0)
            return last_dose_date + timedelta(days=interval)

        elif rule_type == "VARIABLE_SEQUENCE":
            intervals = schedule_rules.get("intervals_in_days", [])
            if previous_doses_count < len(intervals):
                days_until_next = intervals[previous_doses_count]
                return last_dose_date + timedelta(days=days_until_next)

        return None
