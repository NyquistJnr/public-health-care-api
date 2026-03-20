# health_system/urls.py
from django.contrib import admin
from django.urls import path, include

handler404 = 'core.views.global_404'
handler500 = 'core.views.global_500'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('health_system.api_v1_urls')),
]
