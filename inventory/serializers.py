from rest_framework import serializers
from django.db.models import Sum, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from .models import Drug, DrugBatch


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

    @extend_schema_field(serializers.IntegerField())
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

    @extend_schema_field(DrugBatchSerializer(many=True))
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

class ExpiringDrugBatchSerializer(serializers.ModelSerializer):
    drug_name = serializers.CharField(source='drug.name', read_only=True)
    unit = serializers.CharField(source='drug.unit', read_only=True)
    category = serializers.CharField(source='drug.category', read_only=True)
    days_left = serializers.SerializerMethodField()

    class Meta:
        model = DrugBatch
        fields = [
            'id', 
            'drug_name', 
            'category',
            'batch_number', 
            'unit', 
            'remaining_quantity', 
            'expiry_date', 
            'days_left',
            'supplier'
        ]

    @extend_schema_field(serializers.IntegerField())
    def get_days_left(self, obj):
        today = timezone.now().date()
        delta = obj.expiry_date - today
        return delta.days

class ExpiryAnalysisSerializer(serializers.Serializer):
    expiring_30_days = serializers.IntegerField()
    expiring_60_days = serializers.IntegerField()
    expiring_90_days = serializers.IntegerField()
    total_tracked_batches = serializers.IntegerField()
