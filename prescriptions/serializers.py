# prescriptions/serializers.py
from rest_framework import serializers
from django.db import transaction
from .models import Prescription, PrescriptionItem

class PrescriptionStatsResponseSerializer(serializers.Serializer):
    pending_prescriptions = serializers.IntegerField(help_text="Prescriptions ordered but not yet dispensed")
    dispensed = serializers.IntegerField(help_text="Prescriptions fully dispensed")
    low_stock_alerts = serializers.IntegerField(help_text="Drugs & Consumables that have fallen below their global threshold")
    adr_reports = serializers.IntegerField(help_text="Adverse Drug Reaction reports filed")


class PharmacyPieChartSerializer(serializers.Serializer):
    dispensed = serializers.IntegerField(help_text="Number of dispense transactions (Drugs & Consumables) in the period")
    refilled = serializers.IntegerField(help_text="Number of refill/restock transactions (Drugs & Consumables) in the period")
    out_of_stock = serializers.IntegerField(help_text="Number of Drug/Consumable items currently at zero stock")

class PrescriptionItemSerializer(serializers.ModelSerializer):
    medication_name = serializers.CharField(source='get_medication_name', read_only=True)

    class Meta:
        model = PrescriptionItem
        fields = [
            'id', 'inventory_item', 'custom_drug_name', 'medication_name', 'quantity',
            'dosage', 'frequency', 'duration', 'route', 'special_instructions'
        ]

    def validate(self, attrs):
        item = attrs.get('inventory_item')
        custom_name = attrs.get('custom_drug_name')
        
        if not item and not custom_name:
            raise serializers.ValidationError("You must provide either a drug from the inventory or a custom drug name.")
        if item and custom_name:
            raise serializers.ValidationError("Provide either a drug from inventory OR a custom name, not both.")
            
        return attrs

class PrescriptionReadSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    patient_display_id = serializers.CharField(source='patient.patient_profile.patient_id', read_only=True)
    prescribed_by_name = serializers.CharField(source='prescribed_by.get_full_name', read_only=True)
    items = PrescriptionItemSerializer(many=True, read_only=True)

    class Meta:
        model = Prescription
        fields = [
            'id', 'prescription_id', 'patient', 'patient_name', 'patient_display_id', 
            'appointment', 'prescribed_by', 'prescribed_by_name', 
            'priority', 'instructions', 'status', 'created_at', 'items'
        ]

class PrescriptionCreateSerializer(serializers.ModelSerializer):
    items = PrescriptionItemSerializer(many=True, write_only=True, help_text="List of medications")

    class Meta:
        model = Prescription
        fields = ['appointment', 'priority', 'instructions', 'items']

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        user = self.context['request'].user
        
        appointment = validated_data['appointment']
        validated_data['patient'] = appointment.patient
        
        validated_data['prescribed_by'] = user

        prescription = Prescription.objects.create(**validated_data)

        PrescriptionItem.objects.bulk_create([
            PrescriptionItem(prescription=prescription, created_by=user, **item) 
            for item in items_data
        ])

        return prescription

class BasicPrescriptionStatsSerializer(serializers.Serializer):
    dispensed = serializers.IntegerField(help_text="Number of Dispensed")
    pending = serializers.IntegerField(help_text="Number of Pending Prescription")
    cancelled = serializers.IntegerField(help_text="Number of Cancelled Prescription")


class PharmacyActivityItemSerializer(serializers.Serializer):
    activity_type = serializers.CharField(help_text="DISPENSE, REFILL, LOW_STOCK, OUT_OF_STOCK, ADR_REPORT")
    item_name = serializers.CharField()
    description = serializers.CharField()
    timestamp = serializers.DateTimeField()


class PaginatedPharmacyActivitySerializer(serializers.Serializer):
    count = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    current_page = serializers.IntegerField()
    next = serializers.URLField(allow_null=True, required=False)
    previous = serializers.URLField(allow_null=True, required=False)
    results = PharmacyActivityItemSerializer(many=True)
