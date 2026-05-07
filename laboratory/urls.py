# laboratory/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LabRequestViewSet, LabTestViewSet

router = DefaultRouter()
router.register(r'requests', LabRequestViewSet, basename='lab-request')
router.register(r'tests', LabTestViewSet, basename='lab-test')

urlpatterns = [
    path('', include(router.urls)),
]
