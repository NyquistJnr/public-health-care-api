# core/serializers.py
import uuid
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.models import Group
from .models import User, AuditLog

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

class FacilityUserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'staff_id', 'first_name', 'last_name', 'middle_name', 
            'email', 'phone_number', 'role', 
            'is_active', 'suspended_at', 'last_login', 'created_at'
        ]

class PatientCreateSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'middle_name', 
            'email', 'phone_number', 'is_active'
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
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

        return user

class StatusUpdateSerializer(serializers.Serializer):
    is_active = serializers.BooleanField(help_text="Set to true to activate, false to suspend.")

class EmptyStatsSerializer(serializers.Serializer):
    pass

class AuditLogSerializer(serializers.ModelSerializer):
    facility_name = serializers.CharField(source='facility.name', read_only=True, default="System Level")

    class Meta:
        model = AuditLog
        fields = [
            'id', 'actor_name', 'facility', 'facility_name', 'action', 
            'module', 'ip_address', 'endpoint', 'target_object_id', 
            'changes', 'timestamp'
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
