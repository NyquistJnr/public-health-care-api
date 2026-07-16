import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'health_system.settings')
django.setup()

from django.db.models import Value, CharField, F
from django.db.models.functions import Concat, Cast
from core.models import User
from appointments.models import Appointment
from maternal_care.models import ANCVisit, PNCVisit
from nurse_chew.models import HealthPromotion, PostActivity

q1 = User.objects.filter(role='PATIENT', created_by__isnull=False).annotate(
    item_id=Cast('id', CharField(max_length=255)),
    act_type=Value('Patient Registration', CharField(max_length=255)),
    desc=Cast('email', CharField(max_length=255)),
    act_date=F('created_at'),
    perf_by=Concat('created_by__first_name', Value(' '), 'created_by__last_name', output_field=CharField(max_length=255)),
    act_status=Value('COMPLETED', CharField(max_length=255))
).values('item_id', 'act_type', 'desc', 'act_date', 'perf_by', 'act_status')

q2 = ANCVisit.objects.all().annotate(
    item_id=Cast('id', CharField(max_length=255)),
    act_type=Value('Maternal Follow up', CharField(max_length=255)),
    desc=Cast('appointment__appointment_id', CharField(max_length=255)),
    act_date=F('created_at'),
    perf_by=Concat('created_by__first_name', Value(' '), 'created_by__last_name', output_field=CharField(max_length=255)),
    act_status=Value('COMPLETED', CharField(max_length=255))
).values('item_id', 'act_type', 'desc', 'act_date', 'perf_by', 'act_status')

q4 = Appointment.objects.all().annotate(
    item_id=Cast('id', CharField(max_length=255)),
    act_type=Value('Appointment', CharField(max_length=255)),
    desc=Cast('appointment_id', CharField(max_length=255)),
    act_date=F('created_at'),
    perf_by=Concat('created_by__first_name', Value(' '), 'created_by__last_name', output_field=CharField(max_length=255)),
    act_status=Cast('status', CharField(max_length=255))
).values('item_id', 'act_type', 'desc', 'act_date', 'perf_by', 'act_status')

combined = q1.union(q2, q4).order_by('-act_date')
print("COUNT:", combined.count())
print("First item:", list(combined[:1]))
