from rest_framework import serializers
from django.db.models import Sum
from django.utils import timezone
from .models import Drug, DrugBatch, InventoryTransaction


class DrugBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = DrugBatch
        fields = ['id', 'batch_number', 'initial_quantity', 'remaining_quantity', 'purchased_date', 'expiry_date', 'supplier', 'cost_price', 'note', 'created_at']
        read_only_fields = ['id', 'remaining_quantity', 'created_at']

class DrugSerializer(serializers.ModelSerializer):
    total_stock = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    active_batches_count = serializers.SerializerMethodField()

    class Meta:
        model = Drug
        fields = ['id', 'name', 'category', 'unit', 'global_threshold', 'total_stock', 'status', 'active_batches_count']

    def get_total_stock(self, obj):
        today = timezone.now().date()
        total = obj.batches.filter(
            is_active=True, 
            expiry_date__gte=today
        ).aggregate(total=Sum('remaining_quantity'))['total']
        return total or 0

    def get_status(self, obj):
        stock = self.get_total_stock(obj)
        if stock == 0:
            return "OUT_OF_STOCK"
        elif stock <= obj.global_threshold:
            return "LOW_STOCK"
        return "IN_STOCK"

    def get_active_batches_count(self, obj):
        today = timezone.now().date()
        return obj.batches.filter(
            is_active=True, 
            remaining_quantity__gt=0, 
            expiry_date__gte=today
        ).count()

class DrugDetailSerializer(DrugSerializer):
    """Used only for retrieving a single drug by ID"""
    active_batches = serializers.SerializerMethodField()

    class Meta(DrugSerializer.Meta):
        fields = DrugSerializer.Meta.fields + ['active_batches']

    def get_active_batches(self, obj):
        today = timezone.now().date()
        batches = obj.batches.filter(
            is_active=True, 
            remaining_quantity__gt=0, 
            expiry_date__gte=today
        ).order_by('expiry_date')
        return DrugBatchSerializer(batches, many=True).data

class RefillSerializer(serializers.ModelSerializer):
    """Used specifically for adding a new batch"""
    class Meta:
        model = DrugBatch
        fields = ['batch_number', 'initial_quantity', 'purchased_date', 'expiry_date', 'supplier', 'cost_price', 'note']

class DispenseSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)
    note = serializers.CharField(required=False, allow_blank=True)

class FacilityDrugStatsSerializer(serializers.Serializer):
    total_drugs = serializers.IntegerField()
    low_stock_items = serializers.IntegerField()
    out_of_stock = serializers.IntegerField()
    expiring_soon = serializers.IntegerField()
