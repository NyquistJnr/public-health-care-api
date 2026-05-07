# referrals/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ReferralViewSet

router = DefaultRouter()
router.register(r'records', ReferralViewSet, basename='referral')

urlpatterns = [
    path('', include(router.urls)),
]
