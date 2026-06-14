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
        fields = [
            'appointment', 'destination_level', 'referral_type', 'mode_of_transportation', 
            'reason_for_referral', 'clinical_summary', 'receiving_facility', 'receiving_department',
            'mode_of_referral', 'target_doctor_email', 'target_department_email', 
            'email_subject', 'email_body'
        ]

    def validate(self, attrs):
        dest_level = attrs.get('destination_level', 'PRIMARY')
        ref_type = attrs.get('referral_type', 'PHYSICAL')
        transport = attrs.get('mode_of_transportation')

        if transport and ref_type not in ['PHYSICAL', 'EMERGENCY']:
            raise serializers.ValidationError({"mode_of_transportation": "Mode of transportation is only applicable for Physical or Emergency referrals."})

        if dest_level == 'PRIMARY':
            facility = attrs.get('receiving_facility')
            department = attrs.get('receiving_department')

            if not facility and not department:
                raise serializers.ValidationError("For Primary Care referrals, you must select either a Receiving Facility or a Receiving Department.")
            
            if department and not facility:
                attrs['receiving_facility'] = department.facility
            
            user_facility = self.context['request'].user.facility
            if attrs.get('receiving_facility') == user_facility:
                raise serializers.ValidationError({"receiving_facility": "You cannot refer a patient to your own facility."})

            attrs['target_doctor_email'] = None
            attrs['target_department_email'] = None
            attrs['mode_of_referral'] = None

        else:
            doc_email = attrs.get('target_doctor_email')
            dept_email = attrs.get('target_department_email')
            
            if not doc_email and not dept_email:
                raise serializers.ValidationError("External referrals require either a Target Doctor Email or Target Department Email.")
            if doc_email and dept_email:
                raise serializers.ValidationError("Select EITHER a Target Doctor Email OR a Target Department Email, not both.")
            
            if not attrs.get('mode_of_referral'):
                raise serializers.ValidationError({"mode_of_referral": "You must specify if this is being sent via Softcopy or Hardcopy."})

            attrs['receiving_facility'] = None
            attrs['receiving_department'] = None

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
