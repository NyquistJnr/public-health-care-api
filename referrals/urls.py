# referrals/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ReferralViewSet, ExternalReferralActionView

router = DefaultRouter()
router.register(r'records', ReferralViewSet, basename='referral')

urlpatterns = [
    path('external-action/', ExternalReferralActionView.as_view(), name='external_referral_action'),
    path('', include(router.urls)),
]
