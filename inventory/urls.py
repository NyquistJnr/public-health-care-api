from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DrugViewSet, UserFacilityDrugStatsView, SpecificFacilityDrugStatsView, DrugExpiryStatsView

router = DefaultRouter()
router.register(r'drugs', DrugViewSet, basename='drug')

urlpatterns = [
    path('stats/', UserFacilityDrugStatsView.as_view(), name='user-facility-drug-stats'),
    path('facilities/<uuid:facility_id>/stats/', SpecificFacilityDrugStatsView.as_view(), name='specific-facility-drug-stats'),
    path('stats/expiry-analysis/', DrugExpiryStatsView.as_view(), name='drug-expiry-analysis'),
    path('', include(router.urls)),
]
