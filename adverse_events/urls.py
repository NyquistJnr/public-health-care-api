# adverse_events/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AdverseEventViewSet

router = DefaultRouter()
router.register(r'reports', AdverseEventViewSet, basename='adverse-event')

urlpatterns = [
    path('', include(router.urls)),
]
