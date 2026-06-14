# nurse_chew/serializers.py
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from django.utils import timezone
from immunization.models import ImmunizationRecord

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
