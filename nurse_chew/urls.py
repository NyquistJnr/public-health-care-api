# nurse_chew/urls.py
from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    NurseDashboardStatsView,
    PatientAppointmentsView,
    PatientLabRequestsView,
    PatientPrescriptionsView,
    PatientReferralsView,
    MaternalAlertsView,
    ImmunizationsDueView,
    HealthPromotionViewSet,
    PostActivityViewSet,
    ChewStatsView,
    HealthPromotionsTodayView,
    ChewActivityReportStatsView,
    ActivityReportListView
)

router = DefaultRouter()
router.register(r'health-promotions', HealthPromotionViewSet, basename='health-promotions')
router.register(r'post-activities', PostActivityViewSet, basename='post-activities')


urlpatterns = [
    path('stats/', NurseDashboardStatsView.as_view(), name='nurse-stats'),
    path('chew-stats/', ChewStatsView.as_view(), name='chew-stats'),
    path('chew-activity-reports/stats/', ChewActivityReportStatsView.as_view(), name='chew-activity-report-stats'),
    path('chew-activity-reports/', ActivityReportListView.as_view(), name='chew-activity-reports-list'),
    path('health-promotions/today/', HealthPromotionsTodayView.as_view(), name='health-promotions-today'),
    path('alerts/maternal/', MaternalAlertsView.as_view(), name='maternal-alerts'),
    path('alerts/immunizations/', ImmunizationsDueView.as_view(), name='immunizations-due'),
    
    path('patients/<uuid:patient_id>/appointments/', PatientAppointmentsView.as_view(), name='patient-appointments-history'),
    path('patients/<uuid:patient_id>/lab-requests/', PatientLabRequestsView.as_view(), name='patient-labs-history'),
    path('patients/<uuid:patient_id>/prescriptions/', PatientPrescriptionsView.as_view(), name='patient-prescriptions-history'),
    path('patients/<uuid:patient_id>/referrals/', PatientReferralsView.as_view(), name='patient-referrals-history'),
] + router.urls
