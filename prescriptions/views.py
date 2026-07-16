# prescriptions/views.py
from django.utils import timezone
from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db.models import Q, F
from .models import Prescription
from inventory.models import InventoryItem, InventoryTransaction
from inventory.services import dispense_fifo_stock, InsufficientStockError, annotate_stock_levels
from adverse_events.models import AdverseEvent
from core.pagination import StandardResultsSetPagination
from .serializers import (
    PrescriptionReadSerializer, PrescriptionCreateSerializer,
    PrescriptionStatsResponseSerializer, BasicPrescriptionStatsSerializer,
    PaginatedPharmacyActivitySerializer, PharmacyPieChartSerializer,
    PartialDispenseSerializer
)

PHARMACY_STOCK_CATEGORIES = ['DRUG', 'CONSUMABLE']

@extend_schema(tags=["Prescriptions"])
class PrescriptionViewSet(viewsets.ModelViewSet):
    queryset = Prescription.objects.none()

    def get_serializer_class(self):
        if self.action == 'create':
            return PrescriptionCreateSerializer
        return PrescriptionReadSerializer

    @extend_schema(
        summary="List & Filter Prescriptions",
        parameters=[
            OpenApiParameter(name='patient_id', description='Filter by Patient UUID', required=False, type=str),
            OpenApiParameter(name='appointment_id', description='Filter by Appointment UUID', required=False, type=str),
            OpenApiParameter(name='status', description='PENDING, PARTIAL, DISPENSED, CANCELLED', required=False, type=str),
            OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='search', description='Search by Patient Name or PT-ID', required=False, type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = Prescription.objects.filter(patient__facility=self.request.user.facility)
        
        patient_id = self.request.query_params.get('patient_id')
        appointment_id = self.request.query_params.get('appointment_id')
        rx_status = self.request.query_params.get('status')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        search = self.request.query_params.get('search')

        if patient_id:
            qs = qs.filter(patient__id=patient_id)
        if appointment_id:
            qs = qs.filter(appointment__id=appointment_id)
        if rx_status:
            qs = qs.filter(status=rx_status.upper())
        if start_date:
            qs = qs.filter(created_at__gte=start_date)
        if end_date:
            qs = qs.filter(created_at__lte=end_date)
            
        if search:
            qs = qs.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search) |
                Q(patient__patient_profile__patient_id__icontains=search) |
                Q(prescription_id__icontains=search) |
                Q(items__inventory_item__name__icontains=search) |
                Q(items__custom_drug_name__icontains=search)
            ).distinct()

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @extend_schema(
        summary="Dispense Prescription",
        description=(
            "Dispenses the prescription. Can dispense all remaining items or specific quantities."
        ),
        request=PartialDispenseSerializer,
    )
    @action(detail=True, methods=['post'])
    @transaction.atomic
    def dispense(self, request, pk=None):
        prescription = self.get_object()

        if prescription.status in ('DISPENSED', 'CANCELLED'):
            return Response(
                {"detail": f"Prescription is already {prescription.get_status_display()}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = PartialDispenseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        dispense_items = serializer.validated_data.get('items', None)
        force_complete = serializer.validated_data.get('force_complete', False)

        if dispense_items is not None:
            dispense_map = {item['id']: item['quantity'] for item in dispense_items}
        else:
            dispense_map = None

        for item in prescription.items.all():
            qty_to_dispense = 0
            if dispense_map is not None:
                qty_to_dispense = dispense_map.get(item.id, 0)
            else:
                qty_to_dispense = item.quantity - item.dispensed_quantity

            if qty_to_dispense > 0:
                if item.dispensed_quantity + qty_to_dispense > item.quantity:
                    raise ValidationError({"detail": f"Cannot dispense more than prescribed for '{item.get_medication_name()}'."})
                
                # Only deduct stock if it's an inventory item
                if item.inventory_item:
                    try:
                        dispense_fifo_stock(item.inventory_item, qty_to_dispense, request.user)
                    except InsufficientStockError as e:
                        raise ValidationError({"detail": f"Insufficient stock for '{item.get_medication_name()}': {e}"})

                item.dispensed_quantity += qty_to_dispense
                item.save(update_fields=['dispensed_quantity'])

        if force_complete:
            prescription.status = 'DISPENSED'
        else:
            all_items_met = True
            for item in prescription.items.all():
                if item.dispensed_quantity < item.quantity:
                    all_items_met = False
                    break
            
            if all_items_met:
                prescription.status = 'DISPENSED'
            else:
                prescription.status = 'PARTIAL'

        prescription.save(update_fields=['status', 'updated_at'])

        return Response(PrescriptionReadSerializer(prescription).data, status=status.HTTP_200_OK)

@extend_schema(
    tags=["Prescriptions"],
    summary="Get Pharmacy / Dispensary Statistics",
    parameters=[
        OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
    ],
    responses=PrescriptionStatsResponseSerializer
)
class PrescriptionStatsView(APIView):
    def get(self, request):
        facility = request.user.facility

        rx_qs = Prescription.objects.filter(patient__facility=facility)
        adr_qs = AdverseEvent.objects.filter(patient__facility=facility)

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if start_date:
            rx_qs = rx_qs.filter(created_at__gte=start_date)
            adr_qs = adr_qs.filter(created_at__gte=start_date)
        if end_date:
            rx_qs = rx_qs.filter(created_at__lte=end_date)
            adr_qs = adr_qs.filter(created_at__lte=end_date)

        pending = rx_qs.filter(status__in=['PENDING', 'PARTIAL']).count()
        dispensed = rx_qs.filter(status='DISPENSED').count()

        stock_items = annotate_stock_levels(
            InventoryItem.objects.filter(facility=facility, inventory_category__in=PHARMACY_STOCK_CATEGORIES)
        )
        low_stock_count = stock_items.filter(
            annotated_total_stock__gt=0,
            annotated_total_stock__lte=F('calculated_threshold')
        ).count()

        return Response({
            "pending_prescriptions": pending,
            "dispensed": dispensed,
            "low_stock_alerts": low_stock_count,
            "adr_reports": adr_qs.count()
        })

@extend_schema(
    tags=["Prescriptions"],
    summary="Get Basic Prescription Status Counts",
    parameters=[
        OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
    ],
    responses=BasicPrescriptionStatsSerializer
)
class PrescriptionBasicStatsView(APIView):
    def get(self, request):
        qs = Prescription.objects.filter(patient__facility=request.user.facility)
        
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if start_date:
            qs = qs.filter(created_at__gte=start_date)
        if end_date:
            qs = qs.filter(created_at__lte=end_date)

        return Response({
            "dispensed": qs.filter(status='DISPENSED').count(),
            "pending": qs.filter(status='PENDING').count(),
            "cancelled": qs.filter(status='CANCELLED').count()
        })


@extend_schema(
    tags=["Prescriptions"],
    summary="Get Recent Pharmacy Activities & Alerts",
    description=(
        "Returns a paginated timeline of dispensations, refills, ADR reports, and active "
        "low-stock/out-of-stock alerts, across Drugs and Consumables."
    ),
    parameters=[
        OpenApiParameter(name='page', description='Page number', required=False, type=int),
        OpenApiParameter(name='page_size', description='Items per page', required=False, type=int),
    ],
    responses=PaginatedPharmacyActivitySerializer
)
class PharmacyActivitiesView(APIView):
    def get(self, request):
        facility = request.user.facility
        now = timezone.now()
        activities = []

        stock_items = annotate_stock_levels(
            InventoryItem.objects.filter(facility=facility, inventory_category__in=PHARMACY_STOCK_CATEGORIES)
        )

        low_stock_items = stock_items.filter(
            annotated_total_stock__gt=0,
            annotated_total_stock__lte=F('calculated_threshold')
        )
        out_of_stock_items = stock_items.filter(annotated_total_stock=0)

        for item in low_stock_items:
            activities.append({
                "activity_type": "LOW_STOCK",
                "item_name": item.name,
                "description": f"Low stock alert: Only {item.annotated_total_stock} {item.item_type}(s) remaining.",
                "timestamp": now
            })

        for item in out_of_stock_items:
            activities.append({
                "activity_type": "OUT_OF_STOCK",
                "item_name": item.name,
                "description": f"Out of stock alert: {item.name} is completely depleted.",
                "timestamp": now
            })

        transactions = InventoryTransaction.objects.filter(
            batch__item__facility=facility,
            batch__item__inventory_category__in=PHARMACY_STOCK_CATEGORIES
        ).select_related('batch__item').order_by('-created_at')[:200]

        for txn in transactions:
            qty = abs(txn.quantity)
            if txn.transaction_type == 'DISPENSE':
                desc = f"Dispensed {qty} {txn.batch.item.item_type}(s)."
            elif txn.transaction_type == 'REFILL':
                desc = f"Refilled {qty} {txn.batch.item.item_type}(s)."
            else:
                desc = f"Stock adjusted by {txn.quantity}."

            activities.append({
                "activity_type": txn.transaction_type,
                "item_name": txn.batch.item.name,
                "description": desc,
                "timestamp": txn.created_at
            })

        adr_reports = AdverseEvent.objects.filter(patient__facility=facility).select_related(
            'patient', 'suspected_drug'
        ).order_by('-created_at')[:200]

        for report in adr_reports:
            drug_name = report.suspected_drug.name if report.suspected_drug else "Unknown Drug"
            activities.append({
                "activity_type": "ADR_REPORT",
                "item_name": drug_name,
                "description": (
                    f"Adverse event reported for {report.patient.first_name} {report.patient.last_name}: "
                    f"{report.get_severity_display()} {report.reaction_type} ({drug_name})."
                ),
                "timestamp": report.created_at
            })

        activities.sort(key=lambda x: x['timestamp'], reverse=True)

        paginator = StandardResultsSetPagination()
        paginated_activities = paginator.paginate_queryset(activities, request, view=self)

        return paginator.get_paginated_response(paginated_activities)


@extend_schema(
    tags=["Prescriptions"],
    summary="Get Pharmacy Activity Breakdown (Pie Chart)",
    description=(
        "Returns Dispensed and Refilled transaction counts (Drugs & Consumables) for the given "
        "period, plus the current count of Drug/Consumable items that are Out of Stock right now."
    ),
    parameters=[
        OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
    ],
    responses=PharmacyPieChartSerializer
)
class PharmacyPieChartView(APIView):
    def get(self, request):
        facility = request.user.facility
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        txn_qs = InventoryTransaction.objects.filter(
            batch__item__facility=facility,
            batch__item__inventory_category__in=PHARMACY_STOCK_CATEGORIES
        )
        if start_date:
            txn_qs = txn_qs.filter(created_at__gte=start_date)
        if end_date:
            txn_qs = txn_qs.filter(created_at__lte=end_date)

        stock_items = annotate_stock_levels(
            InventoryItem.objects.filter(facility=facility, inventory_category__in=PHARMACY_STOCK_CATEGORIES)
        )

        return Response({
            "dispensed": txn_qs.filter(transaction_type='DISPENSE').count(),
            "refilled": txn_qs.filter(transaction_type='REFILL').count(),
            "out_of_stock": stock_items.filter(annotated_total_stock=0).count()
        })
