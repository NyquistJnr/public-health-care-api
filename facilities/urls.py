# facilities/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FacilityViewSet, StateFacilityStatsView, FacilityStatusToggleView,
    PatientActivityChartView, FacilityITAdminStatsView, FacilityITAdminSystemStatusView,
    FacilityITAdminUserActivityView, FacilityITAdminSystemAlertsView, FacilityITAdminInfoView
)

router = DefaultRouter()
router.register(r'', FacilityViewSet, basename='facility')

urlpatterns = [
    path('', include(router.urls)),
    path('facilities/stats/', StateFacilityStatsView.as_view(), name='state_facility_stats'),
    path('facilities/patient-activity/', PatientActivityChartView.as_view(), name='patient_activity_chart'),
    path('facilities/<uuid:facility_id>/toggle-status/', FacilityStatusToggleView.as_view(), name='facility_toggle_status'),
    path('it-admin/stats/', FacilityITAdminStatsView.as_view(), name='it_admin_stats'),
    path('it-admin/system-status/', FacilityITAdminSystemStatusView.as_view(), name='it_admin_system_status'),
    path('it-admin/user-activity/', FacilityITAdminUserActivityView.as_view(), name='it_admin_user_activity'),
    path('it-admin/system-alerts/', FacilityITAdminSystemAlertsView.as_view(), name='it_admin_system_alerts'),
    path('it-admin/facility-info/', FacilityITAdminInfoView.as_view(), name='it_admin_facility_info'),
]
