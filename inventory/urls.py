from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DrugViewSet, UserFacilityDrugStatsView, SpecificFacilityDrugStatsView

router = DefaultRouter()
router.register(r'drugs', DrugViewSet, basename='drug')

urlpatterns = [
    path('stats/', UserFacilityDrugStatsView.as_view(), name='user-facility-drug-stats'),
    path('facilities/<uuid:facility_id>/stats/', SpecificFacilityDrugStatsView.as_view(), name='specific-facility-drug-stats'),
    path('', include(router.urls)),
]
