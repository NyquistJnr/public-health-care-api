# core/serializers.py
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.models import Group
from .models import User
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
