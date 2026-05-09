# prescriptions/serializers.py
from rest_framework import serializers
from django.db import transaction
from .models import Prescription, PrescriptionItem

class PrescriptionItemSerializer(serializers.ModelSerializer):
    medication_name = serializers.CharField(source='get_medication_name', read_only=True)

    class Meta:
        model = PrescriptionItem
        fields = ['id', 'drug', 'custom_drug_name', 'medication_name', 'dosage', 'frequency', 'duration']

    def validate(self, attrs):
        drug = attrs.get('drug')
        custom_name = attrs.get('custom_drug_name')
        
        if not drug and not custom_name:
            raise serializers.ValidationError("You must provide either a drug from the inventory or a custom drug name.")
        if drug and custom_name:
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
