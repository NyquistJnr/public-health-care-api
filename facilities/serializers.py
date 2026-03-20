# facilities/serializers.py
from rest_framework import serializers
from django.db import transaction, connection
from django.contrib.auth.models import Group
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from core.models import User
from .models import Facility

class FacilitySerializer(serializers.ModelSerializer):
    state = serializers.SerializerMethodField()
    manager_name = serializers.SerializerMethodField()
    it_admin_name = serializers.SerializerMethodField()
    staff_count = serializers.SerializerMethodField()
    patient_count = serializers.SerializerMethodField()

    manager_first_name = serializers.CharField(write_only=True)
    manager_last_name = serializers.CharField(write_only=True)
    manager_email = serializers.EmailField(write_only=True)
    manager_phone = serializers.CharField(write_only=True, required=False, allow_blank=True)

    it_admin_first_name = serializers.CharField(write_only=True)
    it_admin_last_name = serializers.CharField(write_only=True)
    it_admin_email = serializers.EmailField(write_only=True)
    it_admin_phone = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Facility
        fields = [
            'id', 'code', 'name', 'facility_type', 'state', 'lga', 'address', 'level',
            'manager_first_name', 'manager_last_name', 'manager_email', 'manager_phone', 
            'it_admin_first_name', 'it_admin_last_name', 'it_admin_email', 'it_admin_phone', 
            'manager', 'it_admin', 'manager_name', 'it_admin_name', 'patient_count', 'staff_count', 
            'is_active', 'suspended_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'code', 'state', 'manager', 'it_admin', 'is_active', 'suspended_at', 'created_at', 'updated_at']

    def get_state(self, obj) -> str:
        if hasattr(connection, 'tenant') and connection.tenant.schema_name != 'public':
            return connection.tenant.name 
        return "Unknown"

    def get_manager_name(self, obj) -> str | None:
        if obj.manager:
            return f"{obj.manager.first_name} {obj.manager.last_name}".strip()
        return None

    def get_it_admin_name(self, obj) -> str | None:
        if obj.it_admin:
            return f"{obj.it_admin.first_name} {obj.it_admin.last_name}".strip()
        return None

    def get_patient_count(self, obj) -> int | None:
        if 'view' in self.context and self.context['view'].action == 'retrieve':
            return 0
        return None

    def get_staff_count(self, obj) -> int | None:
        if 'view' in self.context and self.context['view'].action == 'retrieve':
            count = obj.staff_members.filter(is_active=True).count()
            
            if obj.manager and obj.manager.is_active:
                is_manager_in_staff_list = obj.staff_members.filter(id=obj.manager.id).exists()
                if not is_manager_in_staff_list:
                    count += 1
                    
            return count
        return None

    def validate(self, attrs):
        m_email = attrs.get('manager_email')
        it_email = attrs.get('it_admin_email')

        errors = {}

        if m_email and User.objects.filter(username__iexact=m_email).exists():
            errors['manager_email'] = f"The email {m_email} is already registered to another user."

        if it_email and User.objects.filter(username__iexact=it_email).exists():
            errors['it_admin_email'] = f"The email {it_email} is already registered to another user."

        if m_email and it_email and m_email.lower() == it_email.lower():
            errors['it_admin_email'] = "The IT Admin and Manager cannot use the same email address."

        if errors:
            raise serializers.ValidationError(errors)

        return super().validate(attrs)

    def _create_facility_user(self, email, first_name, last_name, phone, role, facility, creator):
        """Helper method to create a user, assign them to the facility, and send the invite email."""
        user = User(
            username=email, email=email, first_name=first_name, 
            last_name=last_name, phone_number=phone, role=role, 
            facility=facility, created_by=creator
        )
        user.set_unusable_password()
        user.save()

        try:
            group = Group.objects.get(name=role)
            user.groups.add(group)
        except Group.DoesNotExist:
            pass 

        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = PasswordResetTokenGenerator().make_token(user)
        
        subject = f"Welcome to {facility.name} - Account Setup"
        message = (
            f"Hello {first_name},\n\n"
            f"An account has been created for you as the {role} at {facility.name}.\n\n"
            f"To set your password and access the system, use these details in your app:\n\n"
            f"UID: {uidb64}\nToken: {token}\n\n"
        )
        send_mail(subject, message, "noreply@health.gov.ng", [user.email], fail_silently=True)
        
        return user

    @transaction.atomic
    def create(self, validated_data):
        m_first = validated_data.pop('manager_first_name')
        m_last = validated_data.pop('manager_last_name')
        m_email = validated_data.pop('manager_email')
        m_phone = validated_data.pop('manager_phone', '')

        it_first = validated_data.pop('it_admin_first_name')
        it_last = validated_data.pop('it_admin_last_name')
        it_email = validated_data.pop('it_admin_email')
        it_phone = validated_data.pop('it_admin_phone', '')

        creator = self.context['request'].user

        validated_data['created_by'] = creator
        facility = Facility.objects.create(**validated_data)

        manager_user = self._create_facility_user(
            m_email, m_first, m_last, m_phone, 'DOCTOR', facility, creator
        )
        
        it_admin_user = self._create_facility_user(
            it_email, it_first, it_last, it_phone, 'FACILITY_IT_ADMIN', facility, creator
        )

        facility.manager = manager_user
        facility.it_admin = it_admin_user
        facility.save(update_fields=['manager', 'it_admin'])

        return facility

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        if instance.manager:
            representation['manager_email'] = instance.manager.email
            representation['manager_phone'] = instance.manager.phone_number
        
        if instance.it_admin:
            representation['it_admin_email'] = instance.it_admin.email
            representation['it_admin_phone'] = instance.it_admin.phone_number
            
        return representation
