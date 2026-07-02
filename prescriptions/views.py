# prescriptions/views.py
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models.functions import Coalesce
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db.models import Sum, Q, F, Case, When, FloatField
from .models import Prescription
from inventory.models import InventoryItem, InventoryTransaction
from core.pagination import StandardResultsSetPagination
from .serializers import (
    PrescriptionReadSerializer, PrescriptionCreateSerializer, 
    PrescriptionStatsResponseSerializer, BasicPrescriptionStatsSerializer, 
    PaginatedPharmacyActivitySerializer
)

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
        
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if start_date:
            rx_qs = rx_qs.filter(created_at__gte=start_date)
        if end_date:
            rx_qs = rx_qs.filter(created_at__lte=end_date)

        pending = rx_qs.filter(status__in=['PENDING', 'PARTIAL']).count()
        dispensed = rx_qs.filter(status='DISPENSED').count()

        today = timezone.now().date()
        active_batches_filter = Q(batches__is_active=True) & (
            Q(batches__expiry_date__gte=today) | Q(batches__expiry_date__isnull=True)
        )

        drug_items = InventoryItem.objects.filter(
            facility=facility,
            inventory_category='DRUG'
        ).annotate(
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

        low_stock_count = drug_items.filter(
            annotated_total_stock__gt=0, 
            annotated_total_stock__lte=F('calculated_threshold')
        ).count()

        return Response({
            "pending_prescriptions": pending,
            "dispensed": dispensed,
            "low_stock_alerts": low_stock_count,
            "adr_reports": 0
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
    description="Returns a paginated timeline of dispensations, refills, and active low-stock alerts.",
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

        today = now.date()
        active_batches_filter = Q(batches__is_active=True) & (
            Q(batches__expiry_date__gte=today) | Q(batches__expiry_date__isnull=True)
        )

        drug_items = InventoryItem.objects.filter(
            facility=facility,
            inventory_category='DRUG'
        ).annotate(
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

        low_stock_items = drug_items.filter(
            annotated_total_stock__gt=0, 
            annotated_total_stock__lte=F('calculated_threshold')
        )
        out_of_stock_items = drug_items.filter(annotated_total_stock=0)

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
            batch__item__inventory_category='DRUG'
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

        activities.sort(key=lambda x: x['timestamp'], reverse=True)

        paginator = StandardResultsSetPagination()
        paginated_activities = paginator.paginate_queryset(activities, request, view=self)
        
        return paginator.get_paginated_response(paginated_activities)
