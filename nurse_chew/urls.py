# nurse_chew/urls.py

from django.urls import path
from .views import (
    NurseDashboardStatsView,
    PatientAppointmentsView,
    PatientLabRequestsView,
    PatientPrescriptionsView,
    PatientReferralsView
)

urlpatterns = [
    path('stats/', NurseDashboardStatsView.as_view(), name='nurse-stats'),
    path('patients/<uuid:patient_id>/appointments/', PatientAppointmentsView.as_view(), name='patient-appointments-history'),
    path('patients/<uuid:patient_id>/lab-requests/', PatientLabRequestsView.as_view(), name='patient-labs-history'),
    path('patients/<uuid:patient_id>/prescriptions/', PatientPrescriptionsView.as_view(), name='patient-prescriptions-history'),
    path('patients/<uuid:patient_id>/referrals/', PatientReferralsView.as_view(), name='patient-referrals-history'),
]
