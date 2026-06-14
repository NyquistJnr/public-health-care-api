# prescriptions/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PrescriptionViewSet, PrescriptionStatsView,
    PrescriptionViewSet, PrescriptionBasicStatsView, 
    PharmacyActivitiesView
)

router = DefaultRouter()
router.register(r'orders', PrescriptionViewSet, basename='prescription')

urlpatterns = [
    path('stats/', PrescriptionStatsView.as_view(), name='prescription-stats'),
    path('stats/basic/', PrescriptionBasicStatsView.as_view(), name='prescription-basic-stats'),
    path('activities/', PharmacyActivitiesView.as_view(), name='pharmacy-activities'),
    path('', include(router.urls)),
]
