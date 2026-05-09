# referrals/serializers.py
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from django.db import transaction
from .models import Referral

class ReferralReadSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    patient_display_id = serializers.CharField(source='patient.patient_profile.patient_id', read_only=True)
    referring_facility_name = serializers.CharField(source='referring_facility.name', read_only=True)
    receiving_facility_name = serializers.CharField(source='receiving_facility.name', read_only=True)
    referred_by_name = serializers.CharField(source='referred_by.get_full_name', read_only=True)
    direction = serializers.SerializerMethodField()

    class Meta:
        model = Referral
        fields = [
            'id', 'referral_id', 'appointment', 'patient', 'patient_name', 'patient_display_id',
            'referring_facility', 'referring_facility_name', 'receiving_facility', 'receiving_facility_name',
            'referred_by', 'referred_by_name', 'referral_type', 'reason_for_referral', 
            'clinical_summary', 'status', 'created_at', 'direction'
        ]

    @extend_schema_field(serializers.CharField())
    def get_direction(self, obj):
        request = self.context.get('request')
        if request and hasattr(request.user, 'facility'):
            user_facility = request.user.facility
            if obj.receiving_facility == user_facility:
                return 'inbound'
            elif obj.referring_facility == user_facility:
                return 'outbound'
        return 'unknown'

class ReferralCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Referral
        fields = ['appointment', 'receiving_facility', 'referral_type', 'reason_for_referral', 'clinical_summary']

    def validate(self, attrs):
        if attrs['appointment'].facility == attrs['receiving_facility']:
            raise serializers.ValidationError({"receiving_facility": "You cannot refer a patient to your own facility."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        user = self.context['request'].user
        appointment = validated_data['appointment']
        
        validated_data['patient'] = appointment.patient
        validated_data['referring_facility'] = appointment.facility
        validated_data['referred_by'] = user
        validated_data['created_by'] = user

        return super().create(validated_data)

class ReferralStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Referral
        fields = ['status']
        
    def validate_status(self, value):
        if value not in ['ACCEPTED', 'REJECTED']:
            raise serializers.ValidationError("You can only Accept or Reject a referral.")
        return value
