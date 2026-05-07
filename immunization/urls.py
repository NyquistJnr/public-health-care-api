from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ImmunizationViewSet

router = DefaultRouter()
router.register(r'records', ImmunizationViewSet, basename='immunization')

urlpatterns = [
    path('', include(router.urls)),
]
