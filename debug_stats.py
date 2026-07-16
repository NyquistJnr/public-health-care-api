import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'health_system.settings')
django.setup()

from core.models import User
from appointments.models import Appointment
from maternal_care.models import ANCVisit, PNCVisit
from nurse_chew.models import HealthPromotion, PostActivity

print("Total PATIENTS:", User.objects.filter(role='PATIENT').count())
print("PATIENTS by CHEW:", User.objects.filter(role='PATIENT', created_by__role='CHEW').count())

print("Total COMMUNITY Appointments:", Appointment.objects.filter(visit_type='COMMUNITY').count())
print("COMMUNITY by CHEW:", Appointment.objects.filter(visit_type='COMMUNITY', assigned_to__role='CHEW').count())

print("Total ANC Visits:", ANCVisit.objects.count())
print("ANC by CHEW:", ANCVisit.objects.filter(created_by__role='CHEW').count())

print("Total HealthPromotions:", HealthPromotion.objects.count())
print("HealthPromotions by CHEW:", HealthPromotion.objects.filter(created_by__role='CHEW').count())

print("Total Users in DB:", User.objects.count())
for u in User.objects.all()[:5]:
    print(f"User: {u.email}, Role: {u.role}")

for hp in HealthPromotion.objects.all()[:5]:
    print(f"HP: {hp.title}, created_by role: {hp.created_by.role if hp.created_by else 'None'}")
