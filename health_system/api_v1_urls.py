# health_system/api_v1_urls.py
from django.urls import path, include
from core.urls import (
    auth_patterns,
    user_management_patterns,
    patient_patterns,
    system_patterns,
    stats_patterns
)
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

urlpatterns = [
    path('auth/', include((auth_patterns, 'auth'))),
    path('users/', include((user_management_patterns, 'users'))),
    path('patients/', include((patient_patterns, 'patients'))),
    path('system/', include((system_patterns, 'system'))),
    path('stats/', include((stats_patterns, 'stats'))),

    path('facilities/', include('facilities.urls')),
    path('inventory/', include('inventory.urls')),
    path('appointments/', include('appointments.urls')),
    path('immunization/', include('immunization.urls')),
    path('maternal-care/', include('maternal_care.urls')),
    path('laboratory/', include('laboratory.urls')),
    path('prescriptions/', include('prescriptions.urls')),
    path('consultations/', include('consultations.urls')),
    path('referrals/', include('referrals.urls')),
    path('doctor/', include('doctors.urls')),
    path('nurse/', include('nurse_chew.urls')),
    path('departments/', include('departments.urls')),
    path('adverse-events/', include('adverse_events.urls')),
    
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('docs/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
