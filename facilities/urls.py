# facilities/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import FacilityViewSet, StateFacilityStatsView, FacilityStatusToggleView

router = DefaultRouter()
router.register(r'', FacilityViewSet, basename='facility')

urlpatterns = [
    path('', include(router.urls)),
    path('facilities/stats/', StateFacilityStatsView.as_view(), name='state_facility_stats'),
    path('facilities/<uuid:facility_id>/toggle-status/', FacilityStatusToggleView.as_view(), name='facility_toggle_status'),
]
