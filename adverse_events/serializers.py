# adverse_events/serializers.py
from rest_framework import serializers
from core.models import User
from inventory.models import InventoryItem
from .models import AdverseEvent


class AdverseEventSerializer(serializers.ModelSerializer):
    """Used for listing and as the base for the detail view."""
    patient_name = serializers.SerializerMethodField()
    patient_display_id = serializers.CharField(source='patient.patient_profile.patient_id', read_only=True)
    reported_by_name = serializers.SerializerMethodField()
    suspected_drug_name = serializers.CharField(source='suspected_drug.name', read_only=True)

    class Meta:
        model = AdverseEvent
        fields = [
            'id', 'event_id', 'patient', 'patient_name', 'patient_display_id',
            'reported_by', 'reported_by_name',
            'suspected_drug', 'suspected_drug_name', 'dosage',
            'date_of_reaction', 'stop_date', 'reaction_type', 'severity',
            'detailed_symptoms', 'status', 'created_at'
        ]

    def get_patient_name(self, obj):
        return f"{obj.patient.first_name} {obj.patient.last_name}"

    def get_reported_by_name(self, obj):
        if obj.reported_by:
            return f"{obj.reported_by.first_name} {obj.reported_by.last_name}"
        return None


class AdverseEventDetailSerializer(AdverseEventSerializer):
    """Used for the retrieve (detail) endpoint - adds patient demographics."""
    patient_age = serializers.SerializerMethodField()
    patient_sex = serializers.CharField(source='patient.patient_profile.get_sex_display', read_only=True)

    class Meta(AdverseEventSerializer.Meta):
        fields = AdverseEventSerializer.Meta.fields + ['patient_age', 'patient_sex']

    def get_patient_age(self, obj):
        profile = getattr(obj.patient, 'patient_profile', None)
        return profile.age if profile else None


class AdverseEventWriteSerializer(serializers.ModelSerializer):
    """Used for create/update. `status` cannot be set on create (always starts REPORTED) but is editable afterwards."""
    patient = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role='PATIENT'))
    reported_by = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.exclude(role='PATIENT'), required=False,
        help_text="Defaults to the logged-in user. Pass a UUID to report on behalf of another staff member."
    )
    suspected_drug = serializers.PrimaryKeyRelatedField(queryset=InventoryItem.objects.filter(inventory_category='DRUG'))

    class Meta:
        model = AdverseEvent
        fields = [
            'id', 'event_id', 'patient', 'reported_by', 'suspected_drug', 'dosage',
            'date_of_reaction', 'stop_date', 'reaction_type', 'severity',
            'detailed_symptoms', 'status'
        ]
        read_only_fields = ['id', 'event_id']
        extra_kwargs = {'status': {'required': False}}

    def validate_reported_by(self, value):
        request_user = self.context['request'].user
        if value.facility_id != request_user.facility_id:
            raise serializers.ValidationError("The reporting staff member must belong to your facility.")
        return value

    def create(self, validated_data):
        validated_data.setdefault('reported_by', self.context['request'].user)
        validated_data.pop('status', None)
        return super().create(validated_data)
