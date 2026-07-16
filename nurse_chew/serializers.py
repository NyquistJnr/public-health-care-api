# nurse_chew/serializers.py
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from django.utils import timezone
from immunization.models import ImmunizationRecord
from .models import HealthPromotion, PostActivity

class NurseStatsResponseSerializer(serializers.Serializer):
    waiting_in_queue = serializers.IntegerField(help_text="Patients physically arrived or scheduled for today")
    vitals_pending = serializers.IntegerField(help_text="Patients marked as ARRIVED but without vitals taken")
    maternal_alerts = serializers.IntegerField(help_text="Active pregnancies with documented risk factors")
    vaccines_due = serializers.IntegerField(help_text="Newborns <= 28 days with zero recorded immunizations")

class MaternalAlertItemSerializer(serializers.Serializer):
    alert_type = serializers.CharField(help_text="URGENT_APPOINTMENT, OVERDUE_ANC, OVERDUE_PNC")
    patient_name = serializers.CharField()
    patient_id = serializers.CharField()
    date = serializers.DateField(help_text="The date the appointment is scheduled or the visit was due")
    priority = serializers.CharField()
    details = serializers.CharField(help_text="Context regarding why this is an alert")

class PaginatedMaternalAlertsSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    current_page = serializers.IntegerField()
    next = serializers.URLField(allow_null=True, required=False)
    previous = serializers.URLField(allow_null=True, required=False)
    results = MaternalAlertItemSerializer(many=True)

class ImmunizationDueItemSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    patient_id = serializers.CharField(source='patient.patient_profile.patient_id', read_only=True)
    vaccine_name = serializers.CharField(source='vaccine_given.name', read_only=True)
    next_dose_target = serializers.SerializerMethodField()
    user_friendly_date = serializers.SerializerMethodField()

    class Meta:
        model = ImmunizationRecord
        fields = [
            'id', 'patient_name', 'patient_id', 'vaccine_name', 
            'next_dose_target', 'next_due_date', 'user_friendly_date'
        ]

    @extend_schema_field(serializers.CharField())
    def get_next_dose_target(self, obj):
        next_dose = obj.dose_number + 1
        
        rules = obj.vaccine_given.schedule_rules
        interval_text = ""
        if rules and isinstance(rules, dict):
            if rules.get("type") == "RECURRING":
                interval_text = f" ({rules.get('interval_days')} days interval)"
            elif rules.get("type") == "VARIABLE_SEQUENCE":
                intervals = rules.get("intervals_in_days", [])
                if len(intervals) >= next_dose:
                    interval_text = f" ({intervals[next_dose - 1]} days since last dose)"

        return f"Dose {next_dose}{interval_text}"

    @extend_schema_field(serializers.CharField())
    def get_user_friendly_date(self, obj):
        if not obj.next_due_date:
            return "Unknown"
            
        today = timezone.now().date()
        delta = (obj.next_due_date - today).days

        if delta == 0:
            return "Today"
        elif delta == 1:
            return "Tomorrow"
        elif delta == -1:
            return "Yesterday"
        elif delta < -1:
            return f"{abs(delta)} days ago"
        elif delta <= 14:
            return f"In {delta} days"
        else:
            return obj.next_due_date.strftime('%B %d, %Y')

class HealthPromotionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField(read_only=True)
    assigned_to_names = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = HealthPromotion
        fields = '__all__'
        read_only_fields = ('promotion_id', 'sequence_number', 'created_at', 'updated_at', 'created_by')

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
        return None

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_assigned_to_names(self, obj):
        return [{"id": str(u.id), "name": f"{u.first_name} {u.last_name}".strip()} for u in obj.assigned_to.all()]

    def validate(self, data):
        status = data.get('status', self.instance.status if self.instance else 'DRAFT')
        if status != 'DRAFT':
            required_fields = ['title', 'type', 'location', 'target_audience', 'expected_participants', 'start_date', 'end_date', 'description']
            errors = {}
            for field in required_fields:
                val = data.get(field, getattr(self.instance, field, None) if self.instance else None)
                if val is None or val == '':
                    errors[field] = "This field is required when not in DRAFT status."
            if errors:
                raise serializers.ValidationError(errors)

        st = data.get('start_date', getattr(self.instance, 'start_date', None) if self.instance else None)
        en = data.get('end_date', getattr(self.instance, 'end_date', None) if self.instance else None)
        if st and en and st > en:
            raise serializers.ValidationError({"end_date": "End date must occur after start date."})
        return data

class PostActivitySerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = PostActivity
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by')

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
        return None

    def validate(self, data):
        status = data.get('status', self.instance.status if self.instance else 'DRAFT')
        if status != 'DRAFT':
            required_fields = ['number_of_participants', 'male_count', 'female_count', 'key_messages_delivered', 'outcome_summary', 'challenges']
            errors = {}
            for field in required_fields:
                val = data.get(field, getattr(self.instance, field, None) if self.instance else None)
                if val is None or val == '':
                    errors[field] = "This field is required when not in DRAFT status."
            if errors:
                raise serializers.ValidationError(errors)

        # Allow partial updates
        number_of_participants = data.get('number_of_participants', getattr(self.instance, 'number_of_participants', None) if self.instance else None)
        male_count = data.get('male_count', getattr(self.instance, 'male_count', None) if self.instance else None)
        female_count = data.get('female_count', getattr(self.instance, 'female_count', None) if self.instance else None)
        
        if number_of_participants is not None and male_count is not None and female_count is not None:
            if number_of_participants != male_count + female_count:
                raise serializers.ValidationError({
                    "number_of_participants": "Total participants must equal the sum of male and female counts."
                })
        return data

class ChewStatsResponseSerializer(serializers.Serializer):
    new_registrations = serializers.IntegerField()
    community_visits = serializers.IntegerField()
    maternal_follow_ups = serializers.IntegerField()
    health_promotions = serializers.IntegerField()

class HealthPromotionTodaySerializer(serializers.ModelSerializer):
    assigned_staffs = serializers.SerializerMethodField()
    date_and_time = serializers.DateTimeField(source='start_date')

    class Meta:
        model = HealthPromotion
        fields = ('title', 'type', 'date_and_time', 'assigned_staffs')

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_assigned_staffs(self, obj):
        return [f"{u.first_name} {u.last_name}" for u in obj.assigned_to.all()]

class ChewActivityReportStatsSerializer(serializers.Serializer):
    total_activities = serializers.IntegerField()
    patients_reached = serializers.IntegerField()
    maternal_follow_ups = serializers.IntegerField()
    community_visits = serializers.IntegerField()

class ActivityReportItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    activity_type = serializers.CharField()
    description = serializers.CharField()
    date = serializers.DateTimeField()
    performed_by = serializers.CharField()
    status = serializers.CharField()
