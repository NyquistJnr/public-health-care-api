# inventory/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction
from django.db.models import Sum, Q, F, Case, When, FloatField, Count
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import timedelta
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .models import InventoryItem, ItemBatch, InventoryTransaction
from facilities.models import Facility
from .serializers import (
    InventoryItemSerializer, RefillItemSerializer, DispenseItemSerializer, 
    FacilityDrugStatsSerializer, DrugDetailSerializer, ExpiringDrugBatchSerializer,
    ExpiryAnalysisSerializer
)
from .services import ScheduleEngine

def calculate_facility_inventory_stats(facility):
    items = InventoryItem.objects.filter(facility=facility)
    today = timezone.now().date()
    thirty_days_from_now = today + timedelta(days=30)
    
    total_items = items.count()
    low_stock_count = 0
    out_of_stock_count = 0
    
    for item in items:
        active_batches = item.batches.filter(
            Q(expiry_date__gte=today) | Q(expiry_date__isnull=True),
            is_active=True
        )
        
        stock_data = active_batches.aggregate(
            remaining=Sum('remaining_quantity'),
            initial=Sum('initial_quantity')
        )
        
        total_stock = stock_data['remaining'] or 0
        total_initial = stock_data['initial'] or 0
        
        if item.threshold_type == 'PERCENTAGE':
            calculated_threshold = (total_initial * item.global_threshold) / 100
        else:
            calculated_threshold = item.global_threshold

        if total_stock == 0:
            out_of_stock_count += 1
        elif total_stock <= calculated_threshold:
            low_stock_count += 1

    expiring_soon_count = InventoryItem.objects.filter(
        facility=facility,
        batches__is_active=True,
        batches__remaining_quantity__gt=0,
        batches__expiry_date__gt=today,
        batches__expiry_date__lte=thirty_days_from_now
    ).distinct().count()

    return {
        "total_drugs": total_items, 
        "low_stock_items": low_stock_count,
        "out_of_stock": out_of_stock_count,
        "expiring_soon": expiring_soon_count
    }


@extend_schema_view(
    list=extend_schema(
        tags=["Inventory & Stock Management"], 
        summary="List & Filter Facility Inventory",
        description="Retrieve a paginated list of all inventory items (Drugs, Lab Equipment, Consumables) in the current facility.",
        parameters=[
            OpenApiParameter(name='search', description='Search by item name or type', required=False, type=str),
            OpenApiParameter(name='inventory_category', description='Filter by Category: DRUG, LAB_EQUIPMENT, CONSUMABLE', required=False, type=str),
            OpenApiParameter(name='drug_classification', description='Filter by Class: NORMAL, IMMUNIZATION', required=False, type=str),
            OpenApiParameter(name='status', description='Filter by Status: IN_STOCK, LOW_STOCK, OUT_OF_STOCK', required=False, type=str),
            OpenApiParameter(name='start_date', description='Filter by creation start date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='end_date', description='Filter by creation end date (YYYY-MM-DD)', required=False, type=str),
        ]
    ),
    create=extend_schema(tags=["Inventory & Stock Management"], summary="Register New Inventory Item"),
    retrieve=extend_schema(tags=["Inventory & Stock Management"], summary="Get Inventory Item Details"),
    update=extend_schema(tags=["Inventory & Stock Management"], summary="Update Inventory Catalog Details"),
    partial_update=extend_schema(tags=["Inventory & Stock Management"], summary="Partial Update Item Details"),
    destroy=extend_schema(tags=["Inventory & Stock Management"], summary="Remove Item from Catalog"),
)
class InventoryItemViewSet(viewsets.ModelViewSet):
    queryset = InventoryItem.objects.none()

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return DrugDetailSerializer
        return InventoryItemSerializer

    def get_queryset(self):
        queryset = InventoryItem.objects.filter(facility=self.request.user.facility)
        
        search = self.request.query_params.get('search')
        category = self.request.query_params.get('inventory_category')
        classification = self.request.query_params.get('drug_classification')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        status_param = self.request.query_params.get('status')

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(item_type__icontains=search)
            )

        if category:
            queryset = queryset.filter(inventory_category=category.upper())
            
        if classification:
            queryset = queryset.filter(drug_classification=classification.upper())

        if start_date and end_date:
            queryset = queryset.filter(created_at__date__range=[start_date, end_date])
        elif start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        elif end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)

        if status_param:
            today = timezone.now().date()
            
            active_batches_filter = Q(batches__is_active=True) & (
                Q(batches__expiry_date__gte=today) | Q(batches__expiry_date__isnull=True)
            )

            queryset = queryset.annotate(
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

            status_param = status_param.upper()
            if status_param == 'OUT_OF_STOCK':
                queryset = queryset.filter(annotated_total_stock=0)
            elif status_param == 'LOW_STOCK':
                queryset = queryset.filter(
                    annotated_total_stock__gt=0, 
                    annotated_total_stock__lte=F('calculated_threshold')
                )
            elif status_param == 'IN_STOCK':
                queryset = queryset.filter(annotated_total_stock__gt=F('calculated_threshold'))

        return queryset.order_by('name')

    def perform_create(self, serializer):
        serializer.save(facility=self.request.user.facility, created_by=self.request.user)

    @extend_schema(tags=["Inventory & Stock Management"], summary="Refill Stock (Add new Batch)", request=RefillItemSerializer)
    @action(detail=True, methods=['post'])
    @transaction.atomic
    def refill(self, request, pk=None):
        item = self.get_object()
        serializer = RefillItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        batch = ItemBatch.objects.create(
            item=item,
            remaining_quantity=serializer.validated_data['initial_quantity'],
            created_by=request.user,
            **serializer.validated_data
        )

        InventoryTransaction.objects.create(
            batch=batch,
            transaction_type='REFILL',
            quantity=batch.initial_quantity,
            performed_by=request.user
        )

        return Response({"detail": f"Successfully refilled {batch.initial_quantity} {item.item_type} of {item.name}."}, status=status.HTTP_200_OK)

    @extend_schema(tags=["Inventory & Stock Management"], summary="Dispense Item (FIFO Auto-deduction)", request=DispenseItemSerializer)
    @action(detail=True, methods=['post'])
    @transaction.atomic
    def dispense(self, request, pk=None):
        item = self.get_object()
        serializer = DispenseItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        quantity_to_dispense = serializer.validated_data['quantity']
        today = timezone.now().date()

        active_batches = ItemBatch.objects.filter(
            item=item,
            is_active=True,
            remaining_quantity__gt=0
        ).filter(
            Q(expiry_date__gte=today) | Q(expiry_date__isnull=True)
        ).select_for_update().order_by('expiry_date')

        total_available = sum(batch.remaining_quantity for batch in active_batches)
        if quantity_to_dispense > total_available:
            return Response(
                {"detail": f"Insufficient stock. Requested: {quantity_to_dispense}. Available: {total_available}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        remaining_to_deduct = quantity_to_dispense

        for batch in active_batches:
            if remaining_to_deduct <= 0:
                break

            if batch.remaining_quantity >= remaining_to_deduct:
                batch.remaining_quantity -= remaining_to_deduct
                InventoryTransaction.objects.create(
                    batch=batch, transaction_type='DISPENSE', quantity=-remaining_to_deduct, performed_by=request.user
                )
                batch.save(update_fields=['remaining_quantity', 'updated_at'])
                remaining_to_deduct = 0
            else:
                deducted_from_this_batch = batch.remaining_quantity
                remaining_to_deduct -= deducted_from_this_batch
                batch.remaining_quantity = 0
                InventoryTransaction.objects.create(
                    batch=batch, transaction_type='DISPENSE', quantity=-deducted_from_this_batch, performed_by=request.user
                )
                batch.save(update_fields=['remaining_quantity', 'updated_at'])

        next_due_date = None
        if item.schedule_rules:
            next_due_date = ScheduleEngine.calculate_next_due_date(
                schedule_rules=item.schedule_rules,
                previous_doses_count=serializer.validated_data.get('previous_doses_count', 0),
                last_dose_date=today
            )

        return Response({
            "detail": f"Successfully dispensed {quantity_to_dispense} {item.item_type} of {item.name}.",
            "next_due_date": next_due_date
        }, status=status.HTTP_200_OK)
    
    @extend_schema(
        tags=["Inventory & Stock Management"], 
        summary="List expiring batches in order", 
        parameters=[
            OpenApiParameter(name='inventory_category', description='Filter by Category: DRUG, LAB_EQUIPMENT, CONSUMABLE', required=False, type=str),
            OpenApiParameter(name='drug_classification', description='Filter by Class: NORMAL, IMMUNIZATION', required=False, type=str),
            OpenApiParameter(name='page', description='Page number', required=False, type=int),
            OpenApiParameter(name='page_size', description='Items per page', required=False, type=int),
        ],
        responses=ExpiringDrugBatchSerializer(many=True)
    )
    @action(detail=False, methods=['get'])
    def expiring(self, request):
        today = timezone.now().date()
        batches = ItemBatch.objects.filter(
            item__facility=request.user.facility,
            is_active=True,
            remaining_quantity__gt=0,
            expiry_date__isnull=False
        ).filter(
            expiry_date__gte=today
        ).select_related('item')

        category = request.query_params.get('inventory_category')
        classification = request.query_params.get('drug_classification')

        if category:
            batches = batches.filter(item__inventory_category=category.upper())
            
        if classification:
            batches = batches.filter(item__drug_classification=classification.upper())

        batches = batches.order_by('expiry_date')
        
        page = self.paginate_queryset(batches)
        if page is not None:
            serializer = ExpiringDrugBatchSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = ExpiringDrugBatchSerializer(batches, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(tags=["Inventory & Stock Management"], summary="Get User's Facility Inventory Stats", responses=FacilityDrugStatsSerializer)
class UserFacilityDrugStatsView(APIView):
    def get(self, request):
        stats = calculate_facility_inventory_stats(request.user.facility)
        return Response(stats)


@extend_schema(tags=["Inventory & Stock Management"], summary="Get Specific Facility Inventory Stats", responses=FacilityDrugStatsSerializer)
class SpecificFacilityDrugStatsView(APIView):
    def get(self, request, facility_id):
        facility = get_object_or_404(Facility, id=facility_id)
        stats = calculate_facility_inventory_stats(facility)
        return Response(stats)


class DrugExpiryStatsView(APIView):
    @extend_schema(
        tags=["Inventory & Stock Management"],
        summary="Get expiry buckets for a date range",
        parameters=[
            OpenApiParameter(
                name="start_date", 
                type=OpenApiTypes.DATE, 
                location=OpenApiParameter.QUERY, 
                description="Filter by purchased date start (YYYY-MM-DD)"
            ),
            OpenApiParameter(
                name="end_date", 
                type=OpenApiTypes.DATE, 
                location=OpenApiParameter.QUERY, 
                description="Filter by purchased date end (YYYY-MM-DD)"
            ),
        ],
        responses=ExpiryAnalysisSerializer
    )
    def get(self, request):
        facility = request.user.facility
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        queryset = ItemBatch.objects.filter(
            item__facility=facility,
            is_active=True,
            remaining_quantity__gt=0,
            expiry_date__isnull=False
        )

        if start_date and end_date:
            queryset = queryset.filter(purchased_date__range=[start_date, end_date])

        today = timezone.now().date()
        d30 = today + timedelta(days=30)
        d60 = today + timedelta(days=60)
        d90 = today + timedelta(days=90)

        stats = queryset.aggregate(
            thirty=Count('item', filter=Q(expiry_date__lte=d30), distinct=True),
            sixty=Count('item', filter=Q(expiry_date__lte=d60), distinct=True),
            ninety=Count('item', filter=Q(expiry_date__lte=d90), distinct=True),
            total=Count('id')
        )

        data = {
            "expiring_30_days": stats['thirty'],
            "expiring_60_days": stats['sixty'],
            "expiring_90_days": stats['ninety'],
            "total_tracked_batches": stats['total']
        }

        return Response(data)
