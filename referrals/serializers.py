# referrals/serializers.py
from rest_framework import serializers
from django.db import transaction
from .models import Referral
from facilities.models import Facility

class ReferralReadSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    patient_display_id = serializers.CharField(source='patient.patient_profile.patient_id', read_only=True)
    referring_facility_name = serializers.CharField(source='referring_facility.name', read_only=True)
    receiving_facility_name = serializers.CharField(source='receiving_facility.name', read_only=True)
    referred_by_name = serializers.CharField(source='referred_by.get_full_name', read_only=True)

    class Meta:
        model = Referral
        fields = [
            'id', 'referral_id', 'appointment', 'patient', 'patient_name', 'patient_display_id',
            'referring_facility', 'referring_facility_name', 'receiving_facility', 'receiving_facility_name',
            'referred_by', 'referred_by_name', 'referral_type', 'reason_for_referral', 
            'clinical_summary', 'status', 'created_at'
        ]

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
