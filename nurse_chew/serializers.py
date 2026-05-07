# nurse_chew/serializers.py
from rest_framework import serializers

class NurseStatsResponseSerializer(serializers.Serializer):
    waiting_in_queue = serializers.IntegerField(help_text="Patients physically arrived or scheduled for today")
    vitals_pending = serializers.IntegerField(help_text="Patients marked as ARRIVED but without vitals taken")
    maternal_alerts = serializers.IntegerField(help_text="Active pregnancies with documented risk factors")
    vaccines_due = serializers.IntegerField(help_text="Newborns <= 28 days with zero recorded immunizations")
