# laboratory/serializers.py

from rest_framework import serializers
from django.db import transaction
from .models import LabRequest, LabTest
from core.models import User
from inventory.models import InventoryItem

class LabTestItemSerializer(serializers.ModelSerializer):
    linked_item = serializers.PrimaryKeyRelatedField(
        queryset=InventoryItem.objects.filter(inventory_category__in=['LAB_EQUIPMENT', 'CONSUMABLE']),
        required=False,
        allow_null=True,
        help_text="Optional. The specific test kit or consumable linked to this test.",
    )
    linked_item_name = serializers.CharField(source='linked_item.name', read_only=True, default=None)

    class Meta:
        model = LabTest
        fields = [
            'id', 'test_name', 'linked_item', 'linked_item_name', 'sample_type',
            'test_status', 'result_value', 'result_unit', 'test_method',
            'result_interpretation', 'result_notes', 'result_date'
        ]
        read_only_fields = [
            'id', 'test_status', 'result_value', 'result_unit',
            'test_method', 'result_interpretation', 'result_notes', 'result_date'
        ]

class LabRequestReadSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    patient_display_id = serializers.CharField(source='patient.patient_profile.patient_id', read_only=True)
    requested_by_name = serializers.CharField(source='requested_by.get_full_name', read_only=True)
    tests = LabTestItemSerializer(many=True, read_only=True)

    class Meta:
        model = LabRequest
        fields = ['id', 'request_id', 'patient', 'patient_name', 'patient_display_id', 
                  'appointment', 'recorded_by', 'requested_by', 'requested_by_name', 
                  'priority', 'clinical_notes', 'status', 'created_at', 'tests']

class LabRequestCreateSerializer(serializers.ModelSerializer):
    tests = LabTestItemSerializer(many=True, write_only=True, help_text="List of tests to perform")
    requested_by = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.exclude(role='PATIENT'), 
        required=False, 
        allow_null=True,
        help_text="Optional. Defaults to the logged-in user if left blank."
    )

    class Meta:
        model = LabRequest
        fields = ['appointment', 'requested_by', 'priority', 'clinical_notes', 'tests']

    @transaction.atomic
    def create(self, validated_data):
        tests_data = validated_data.pop('tests')
        user = self.context['request'].user
        
        requested_by = validated_data.pop('requested_by', None)
        if not requested_by:
            requested_by = user

        patient = validated_data['appointment'].patient

        lab_request = LabRequest.objects.create(
            patient=patient,
            recorded_by=user,
            requested_by=requested_by,
            created_by=user,
            **validated_data
        )

        LabTest.objects.bulk_create([
            LabTest(lab_request=lab_request, created_by=user, **test) 
            for test in tests_data
        ])

        return lab_request

class LabResultSubmitSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabTest
        fields = ['result_value', 'result_unit', 'test_method', 'result_interpretation', 'result_notes']
        
    def validate(self, attrs):
        if not attrs.get('result_value'):
            raise serializers.ValidationError({"result_value": "A result value is required to submit a result."})
        return attrs

class LabTestStatsResponseSerializer(serializers.Serializer):
    pending_tests = serializers.IntegerField()
    in_progress = serializers.IntegerField()
    completed = serializers.IntegerField()

class LabRequestStatsResponseSerializer(serializers.Serializer):
    pending_requests = serializers.IntegerField()
    in_progress = serializers.IntegerField()
    completed = serializers.IntegerField()

class InventoryAlertItemSerializer(serializers.Serializer):
    item_id = serializers.UUIDField()
    item_name = serializers.CharField()
    category = serializers.CharField()
    current_stock = serializers.IntegerField()
    threshold = serializers.IntegerField()
    item_type = serializers.CharField(source='unit')

class OverallLabStatsResponseSerializer(serializers.Serializer):
    pending_lab_requests = serializers.IntegerField()
    in_progress = serializers.IntegerField()
    completed = serializers.IntegerField()
    inventory_alert_count = serializers.IntegerField()
    inventory_alerts = InventoryAlertItemSerializer(many=True)
