# appointments/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AppointmentViewSet, VitalsViewSet

router = DefaultRouter()
router.register(r'appointments', AppointmentViewSet, basename='appointment')
router.register(r'vitals', VitalsViewSet, basename='vitals')

urlpatterns = [
    path('awaiting-vitals/', AppointmentViewSet.as_view({'get': 'awaiting_vitals'}), name='awaiting-vitals'),
    path('', include(router.urls)),
]
