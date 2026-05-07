# doctors/urls.py
from django.urls import path
from .views import DoctorAllLabRequestsView, DoctorStatsView, DoctorPendingLabsView, DoctorAlertsView

urlpatterns = [
    path('stats/', DoctorStatsView.as_view(), name='doctor-stats'),
    path('pending-labs/', DoctorPendingLabsView.as_view(), name='doctor-pending-labs'),
    path('alerts/', DoctorAlertsView.as_view(), name='doctor-alerts'),
    path('lab-requests/', DoctorAllLabRequestsView.as_view(), name='doctor-all-lab-requests'),
]
