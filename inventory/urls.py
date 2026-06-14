# inventory/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    InventoryItemViewSet,
    SpecificFacilityInventoryStatsView, 
    DrugExpiryStatsView,
    InventoryComprehensiveStatsView
)

router = DefaultRouter()
router.register(r'items', InventoryItemViewSet, basename='inventory-item')

urlpatterns = [
    path('stats/comprehensive/', InventoryComprehensiveStatsView.as_view(), name='inventory-comprehensive-stats'),
    path('stats/expiry/', DrugExpiryStatsView.as_view(), name='inventory-expiry-stats'),
    path('stats/facility/<uuid:facility_id>/', SpecificFacilityInventoryStatsView.as_view(), name='specific-facility-inventory-stats'),
    path('', include(router.urls)),
]
