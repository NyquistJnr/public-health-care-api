from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from .models import Drug, DrugBatch, InventoryTransaction
from facilities.models import Facility
from .serializers import DrugSerializer, RefillSerializer, DispenseSerializer, FacilityDrugStatsSerializer, DrugDetailSerializer

def calculate_facility_drug_stats(facility):
    drugs = Drug.objects.filter(facility=facility)
    today = timezone.now().date()
    thirty_days_from_now = today + timedelta(days=30)
    
    total_drugs = drugs.count()
    low_stock_count = 0
    out_of_stock_count = 0
    
    for drug in drugs:
        stock = drug.batches.filter(
            is_active=True, 
            expiry_date__gte=today
        ).aggregate(total=Sum('remaining_quantity'))['total'] or 0
        
        if stock == 0:
            out_of_stock_count += 1
        elif stock <= drug.global_threshold:
            low_stock_count += 1

    expiring_soon_count = Drug.objects.filter(
        facility=facility,
        batches__is_active=True,
        batches__remaining_quantity__gt=0,
        batches__expiry_date__gt=today,
        batches__expiry_date__lte=thirty_days_from_now
    ).distinct().count()

    return {
        "total_drugs": total_drugs,
        "low_stock_items": low_stock_count,
        "out_of_stock": out_of_stock_count,
        "expiring_soon": expiring_soon_count
    }

@extend_schema_view(
    list=extend_schema(tags=["Drug Inventory"], summary="List all drugs and current stock"),
    create=extend_schema(tags=["Drug Inventory"], summary="Add a new drug to the catalog"),
    retrieve=extend_schema(tags=["Drug Inventory"], summary="Get specific drug details"),
    update=extend_schema(tags=["Drug Inventory"], summary="Update drug catalog details"),
    partial_update=extend_schema(tags=["Drug Inventory"], summary="Partial update drug details"),
    destroy=extend_schema(tags=["Drug Inventory"], summary="Remove drug from catalog"),
)
class DrugViewSet(viewsets.ModelViewSet):
    queryset = Drug.objects.none()

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return DrugDetailSerializer
        return DrugSerializer

    def get_queryset(self):
        return Drug.objects.filter(facility=self.request.user.facility).order_by('name')

    def perform_create(self, serializer):
        serializer.save(facility=self.request.user.facility, created_by=self.request.user)

    @extend_schema(tags=["Drug Inventory"], summary="Refill Drug (Add new Batch)", request=RefillSerializer)
    @action(detail=True, methods=['post'])
    @transaction.atomic
    def refill(self, request, pk=None):
        drug = self.get_object()
        serializer = RefillSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        batch = DrugBatch.objects.create(
            drug=drug,
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

        return Response({"detail": f"Successfully refilled {batch.initial_quantity} {drug.unit} of {drug.name}."}, status=status.HTTP_200_OK)

    @extend_schema(tags=["Drug Inventory"], summary="Dispense Drug (FIFO Auto-deduction)", request=DispenseSerializer)
    @action(detail=True, methods=['post'])
    @transaction.atomic
    def dispense(self, request, pk=None):
        drug = self.get_object()
        serializer = DispenseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        quantity_to_dispense = serializer.validated_data['quantity']
        today = timezone.now().date()

        active_batches = DrugBatch.objects.filter(
            drug=drug,
            is_active=True,
            remaining_quantity__gt=0,
            expiry_date__gte=today
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

        return Response({"detail": f"Successfully dispensed {quantity_to_dispense} {drug.unit} of {drug.name}."}, status=status.HTTP_200_OK)

@extend_schema(tags=["Drug Inventory"], summary="Get User's Facility Drug Stats", responses=FacilityDrugStatsSerializer)
class UserFacilityDrugStatsView(APIView):
    
    def get(self, request):
        stats = calculate_facility_drug_stats(request.user.facility)
        return Response(stats)


@extend_schema(tags=["Drug Inventory"], summary="Get Specific Facility Drug Stats", responses=FacilityDrugStatsSerializer)
class SpecificFacilityDrugStatsView(APIView):
    
    def get(self, request, facility_id):
        facility = get_object_or_404(Facility, id=facility_id)
        stats = calculate_facility_drug_stats(facility)
        return Response(stats)
