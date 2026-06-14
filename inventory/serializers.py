# inventory/serializers.py
from rest_framework import serializers
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from .models import InventoryItem, ItemBatch, InventoryTransaction

class ItemBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemBatch
        fields = ['id', 'batch_number', 'initial_quantity', 'remaining_quantity', 'purchased_date', 'expiry_date', 'supplier', 'cost_price', 'note', 'created_at']
        read_only_fields = ['id', 'remaining_quantity', 'created_at']

class InventoryItemSerializer(serializers.ModelSerializer):
    total_stock = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = InventoryItem
        fields = [
            'id', 'name', 'inventory_category', 'drug_classification', 
            'item_type', 'global_threshold', 'schedule_rules', 
            'total_stock', 'status'
        ]

    @extend_schema_field(serializers.IntegerField())
    def get_total_stock(self, obj):
        today = timezone.now().date()
        total = obj.batches.filter(
            Q(expiry_date__gte=today) | Q(expiry_date__isnull=True),
            is_active=True
        ).aggregate(total=Sum('remaining_quantity'))['total']
        return total or 0

    @extend_schema_field(serializers.CharField())
    def get_status(self, obj):
        stock = self.get_total_stock(obj)
        if stock == 0:
            return "OUT_OF_STOCK"
        elif stock <= obj.global_threshold:
            return "LOW_STOCK"
        return "IN_STOCK"


class DrugDetailSerializer(InventoryItemSerializer):
    """Used only for retrieving a single item by ID, includes batch breakdown"""
    active_batches = serializers.SerializerMethodField()

    class Meta(InventoryItemSerializer.Meta):
        fields = InventoryItemSerializer.Meta.fields + ['active_batches']

    @extend_schema_field(ItemBatchSerializer(many=True))
    def get_active_batches(self, obj):
        today = timezone.now().date()
        batches = obj.batches.filter(
            is_active=True, 
            remaining_quantity__gt=0
        ).filter(
            Q(expiry_date__gte=today) | Q(expiry_date__isnull=True)
        ).order_by(Coalesce('expiry_date', 'created_at'))
        
        return ItemBatchSerializer(batches, many=True).data


class RefillItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemBatch
        fields = ['batch_number', 'initial_quantity', 'purchased_date', 'expiry_date', 'supplier', 'cost_price', 'note']


class DispenseItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)
    patient_id = serializers.UUIDField(required=False, help_text="Required if dispensing a scheduled drug")
    previous_doses_count = serializers.IntegerField(default=0, help_text="Number of times patient has taken this previously")
    note = serializers.CharField(required=False, allow_blank=True)


class FacilityDrugStatsSerializer(serializers.Serializer):
    total_drugs = serializers.IntegerField(help_text="Total distinct inventory items")
    low_stock_items = serializers.IntegerField()
    out_of_stock = serializers.IntegerField()
    expiring_soon = serializers.IntegerField(help_text="Items with batches expiring in <= 30 days")


class ExpiringDrugBatchSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_type = serializers.CharField(source='item.item_type', read_only=True)
    category = serializers.CharField(source='item.get_inventory_category_display', read_only=True)
    days_left = serializers.SerializerMethodField()

    class Meta:
        model = ItemBatch
        fields = [
            'id', 
            'item_name', 
            'category',
            'batch_number', 
            'item_type', 
            'remaining_quantity', 
            'expiry_date', 
            'days_left',
            'supplier'
        ]

    @extend_schema_field(serializers.IntegerField())
    def get_days_left(self, obj):
        if not obj.expiry_date:
            return 9999
        today = timezone.now().date()
        delta = obj.expiry_date - today
        return delta.days


class ExpiryAnalysisSerializer(serializers.Serializer):
    expiring_30_days = serializers.IntegerField()
    expiring_60_days = serializers.IntegerField()
    expiring_90_days = serializers.IntegerField()
    total_tracked_batches = serializers.IntegerField(help_text="Total active batches with an expiry date")
