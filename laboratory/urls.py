# laboratory/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LabRequestViewSet, 
    LabTestViewSet, 
    LabTestStatsView, 
    LabRequestStatsView, 
    OverallLabStatsView
)

router = DefaultRouter()
router.register(r'requests', LabRequestViewSet, basename='lab-request')
router.register(r'tests', LabTestViewSet, basename='lab-test')

urlpatterns = [
    path('stats/tests/', LabTestStatsView.as_view(), name='lab-test-stats'),
    path('stats/requests/', LabRequestStatsView.as_view(), name='lab-request-stats'),
    path('stats/overall/', OverallLabStatsView.as_view(), name='overall-lab-stats'),
    path('', include(router.urls)),
]
