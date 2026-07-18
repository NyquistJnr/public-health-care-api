# core/serializers.py
import uuid
from django.db import transaction
from drf_spectacular.utils import extend_schema_field, inline_serializer
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.models import Group
from .models import User, AuditLog, PatientProfile
from facilities.models import Facility

class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    email = serializers.EmailField()

    default_error_messages = {
        'no_active_account': 'Incorrect Email and Password'
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'username' in self.fields:
            del self.fields['username']

    def validate(self, attrs):
        attrs['username'] = attrs.get('email')
        data = super().validate(attrs)
        user = self.user
        
        data['user'] = {
            'id': str(user.id),
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role': user.role,
            'profile_picture': user.profile_picture if user.profile_picture else None,
        }
        
        return data

class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

class ResetPasswordSerializer(serializers.Serializer):
    uidb64 = serializers.CharField(write_only=True)
    token = serializers.CharField(write_only=True)
    
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs

class UserInviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'staff_id', 'first_name', 'last_name', 'middle_name', 
            'email', 'phone_number', 'role', 'is_active'
        ]
        read_only_fields = ['id', 'staff_id']

    def create(self, validated_data):
        email = validated_data.get('email')
        
        user = User(**validated_data)
        user.username = email
        user.set_unusable_password() 
        user.save()

        try:
            group = Group.objects.get(name=user.role)
            user.groups.add(group)
        except Group.DoesNotExist:
            pass 

        return user

class StateAdminUserInviteSerializer(UserInviteSerializer):
    facility_id = serializers.PrimaryKeyRelatedField(
        queryset=Facility.objects.all(),
        source='facility',
        write_only=True
    )

    class Meta(UserInviteSerializer.Meta):
        fields = UserInviteSerializer.Meta.fields + ['facility_id']


class FacilityUserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'staff_id', 'first_name', 'last_name', 'middle_name', 
            'email', 'phone_number', 'role', 
            'is_active', 'suspended_at', 'last_login', 'created_at'
        ]

class PatientProfileSerializer(serializers.ModelSerializer):
    age = serializers.IntegerField(read_only=True)
    age_group = serializers.CharField(read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PatientProfile
        exclude = ['user', 'sequence_number']
        read_only_fields = ['patient_id', 'created_at', 'updated_at', 'created_by']

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
        return "System Process"

class PatientSerializer(serializers.ModelSerializer):
    """Used for listing and retrieving patient data"""
    profile = PatientProfileSerializer(source='patient_profile', read_only=True)
    current_maternal_episode = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'middle_name', 
            'email', 'phone_number', 'address', 'state', 'is_active',
            'profile', 'current_maternal_episode', 'created_at', 'updated_at'
        ]
        read_only_fields = fields

    @extend_schema_field(
        inline_serializer(
            name='CurrentMaternalEpisodeSummary',
            fields={
                'episode_id': serializers.CharField(),
                'status': serializers.CharField(), 
                'last_menstrual_period': serializers.DateField(allow_null=True),
                'expected_date_of_delivery': serializers.DateField(allow_null=True),
                'gravida': serializers.IntegerField(),
                'parity': serializers.IntegerField(),
            },
            allow_null=True
        )
    )
    def get_current_maternal_episode(self, obj):
        if hasattr(obj, 'prefetched_maternal_episodes'):
            episode = obj.prefetched_maternal_episodes[0] if obj.prefetched_maternal_episodes else None
        else:
            episode = obj.pregnancies.filter(status__in=['ACTIVE', 'DELIVERED']).order_by('-created_at').first()

        if episode:
            return {
                "episode_id": episode.episode_id,
                "status": episode.status,
                "last_menstrual_period": episode.last_menstrual_period,
                "expected_date_of_delivery": episode.expected_date_of_delivery,
                "gravida": episode.gravida,
                "parity": episode.parity
            }
        return None

class PatientCreateSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    sex = serializers.ChoiceField(choices=PatientProfile.SEX_CHOICES, write_only=True)
    date_of_birth = serializers.DateField(write_only=True)
    lga = serializers.CharField(max_length=100, write_only=True, required=False)
    ward = serializers.CharField(max_length=100, write_only=True, required=False)
    next_of_kin_name = serializers.CharField(max_length=255, write_only=True, required=False)
    next_of_kin_phone = serializers.CharField(max_length=20, write_only=True, required=False)
    insurance_status = serializers.ChoiceField(choices=PatientProfile.INSURANCE_STATUS_CHOICES, write_only=True, required=False)
    insurance_provider = serializers.CharField(max_length=255, write_only=True, required=False)
    insurance_package = serializers.CharField(max_length=255, write_only=True, required=False)
    coverage_status = serializers.CharField(max_length=100, write_only=True, required=False)
    allergies = serializers.CharField(write_only=True, required=False)
    chronic_conditions = serializers.CharField(write_only=True, required=False)
    notes = serializers.CharField(write_only=True, required=False)
    blood_group = serializers.ChoiceField(choices=PatientProfile.BLOOD_GROUP_CHOICES, write_only=True, required=False)
    genotype = serializers.ChoiceField(choices=PatientProfile.GENOTYPE_CHOICES, write_only=True, required=False)
    profile = PatientProfileSerializer(source='patient_profile', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'middle_name', 
            'email', 'phone_number', 'address', 'state', 'is_active',
            'sex', 'date_of_birth', 'lga', 'ward', 'next_of_kin_name', 'next_of_kin_phone',
            'insurance_status', 'insurance_provider', 'insurance_package', 'coverage_status',
            'allergies', 'chronic_conditions', 'notes',
            'blood_group', 'genotype',
            'profile' 
        ]
        read_only_fields = ['id']

    @transaction.atomic
    def create(self, validated_data):
        profile_fields = [
            'sex', 'date_of_birth', 'lga', 'ward', 'next_of_kin_name', 'next_of_kin_phone',
            'insurance_status', 'insurance_provider', 'insurance_package', 'coverage_status',
            'allergies', 'chronic_conditions', 'notes',
            'blood_group', 'genotype'
        ]
        profile_data = {}
        for field in profile_fields:
            if field in validated_data:
                profile_data[field] = validated_data.pop(field)

        email = validated_data.get('email', '')
        username = email if email else f"patient_{uuid.uuid4().hex[:10]}"
        
        user = User(**validated_data)
        user.username = username
        user.role = 'PATIENT'
        user.set_unusable_password() 
        user.save()
        try:
            group = Group.objects.get(name='PATIENT')
            user.groups.add(group)
        except Group.DoesNotExist:
            pass 

        request = self.context.get('request')
        creator = request.user if request else None

        PatientProfile.objects.create(
            user=user,
            created_by=creator,
            **profile_data
        )

        return user

class StatusUpdateSerializer(serializers.Serializer):
    is_active = serializers.BooleanField(help_text="Set to true to activate, false to suspend.")

class EmptyStatsSerializer(serializers.Serializer):
    pass

class AuditLogSerializer(serializers.ModelSerializer):
    facility_name = serializers.CharField(source='facility.name', read_only=True, default="System Level")
    is_read = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = AuditLog
        fields = [
            'id', 'actor_name', 'facility', 'facility_name', 'action', 
            'module', 'ip_address', 'endpoint', 'target_object_id', 
            'changes', 'timestamp', 'is_read'
        ]

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'staff_id', 'first_name', 'last_name', 'middle_name', 
            'email', 'phone_number', 'address', 'city', 'state', 'country', 
            'profile_picture', 'role', 'is_active', 'last_login', 'created_at'
        ]
        read_only_fields = [
            'id', 'staff_id', 'role', 'is_active', 'last_login', 'created_at'
        ]

    def validate_email(self, value):
        """Ensure that if they change their email, it isn't taken by someone else."""
        user = self.context['request'].user
        if User.objects.exclude(pk=user.pk).filter(email__iexact=value).exists():
            raise serializers.ValidationError("This email address is already in use.")
        return value

    def update(self, instance, validated_data):
        """Intercept the save to ensure the internal username matches the new email."""
        email = validated_data.get('email', instance.email)
        
        if email != instance.email:
            instance.username = email
            
        return super().update(instance, validated_data)

class PatientUpdateSerializer(serializers.ModelSerializer):
    """Handles partial updates for both User and PatientProfile simultaneously"""
    
    email = serializers.EmailField(required=False, allow_blank=True)
    sex = serializers.ChoiceField(choices=PatientProfile.SEX_CHOICES, required=False)
    date_of_birth = serializers.DateField(required=False)
    lga = serializers.CharField(max_length=100, required=False, allow_blank=True)
    ward = serializers.CharField(max_length=100, required=False, allow_blank=True)
    next_of_kin_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    next_of_kin_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    insurance_status = serializers.ChoiceField(choices=PatientProfile.INSURANCE_STATUS_CHOICES, required=False)
    insurance_provider = serializers.CharField(max_length=255, required=False, allow_blank=True)
    insurance_package = serializers.CharField(max_length=255, required=False, allow_blank=True)
    coverage_status = serializers.CharField(max_length=100, required=False, allow_blank=True)
    allergies = serializers.CharField(required=False, allow_blank=True)
    chronic_conditions = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    blood_group = serializers.ChoiceField(choices=PatientProfile.BLOOD_GROUP_CHOICES, required=False)
    genotype = serializers.ChoiceField(choices=PatientProfile.GENOTYPE_CHOICES, required=False)
    
    profile = PatientProfileSerializer(source='patient_profile', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'middle_name', 
            'email', 'phone_number', 'address', 'state', 'is_active',
            'sex', 'date_of_birth', 'lga', 'ward', 'next_of_kin_name', 'next_of_kin_phone',
            'insurance_status', 'insurance_provider', 'insurance_package', 'coverage_status',
            'allergies', 'chronic_conditions', 'notes', 'blood_group', 'genotype',
            'profile'
        ]
        read_only_fields = ['id']

    @transaction.atomic
    def update(self, instance, validated_data):
        profile_fields = [
            'sex', 'date_of_birth', 'lga', 'ward', 'next_of_kin_name', 'next_of_kin_phone',
            'insurance_status', 'insurance_provider', 'insurance_package', 'coverage_status',
            'allergies', 'chronic_conditions', 'notes', 'blood_group', 'genotype'
        ]
        
        profile_data = {}
        for field in profile_fields:
            if field in validated_data:
                profile_data[field] = validated_data.pop(field)

        email = validated_data.get('email')
        if email is not None:
            validated_data['username'] = email if email else instance.username
            
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.updated_by = self.context['request'].user
        instance.save()

        if profile_data:
            profile = getattr(instance, 'patient_profile', None)
            if profile:
                for attr, value in profile_data.items():
                    setattr(profile, attr, value)
                profile.updated_by = self.context['request'].user
                profile.save()

        return instance


class PatientRecentAppointmentSerializer(PatientSerializer):
    recent_appointment_status = serializers.SerializerMethodField()
    recent_appointment_date = serializers.SerializerMethodField()

    class Meta(PatientSerializer.Meta):
        fields = PatientSerializer.Meta.fields + ['recent_appointment_status', 'recent_appointment_date']
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_recent_appointment_status(self, obj):
        if hasattr(obj, 'prefetched_latest_appointments') and obj.prefetched_latest_appointments:
            apt = obj.prefetched_latest_appointments[0]
            if hasattr(apt, 'prefetched_referrals') and apt.prefetched_referrals:
                return "Referred"
            
            if apt.status in ['SCHEDULED', 'ARRIVED', 'VITALS_DONE']:
                return "Waiting"
            elif apt.status in ['IN_CONSULTATION', 'COMPLETED']:
                return "Seen"
            return apt.status.capitalize() if apt.status else None
        return None

    @extend_schema_field(serializers.DateField(allow_null=True))
    def get_recent_appointment_date(self, obj):
        if hasattr(obj, 'prefetched_latest_appointments') and obj.prefetched_latest_appointments:
            return obj.prefetched_latest_appointments[0].appointment_date
        return None
