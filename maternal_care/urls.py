# maternal_care/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    MaternalCareEpisodeViewSet, ANCVisitViewSet,
    PNCVisitViewSet, PNCNewbornAssessmentViewSet,
    MaternalScheduleRuleViewSet, AppointmentForANCView,
    AppointmentForPNCView, UpcomingMaternalFollowUpsView,
    DeliveryViewSet
)

router = DefaultRouter()
router.register(r'global-rules', MaternalScheduleRuleViewSet, basename='maternal-schedule-rule')
router.register(r'episodes', MaternalCareEpisodeViewSet, basename='maternal-episode')
router.register(r'anc-visits', ANCVisitViewSet, basename='anc-visit')
router.register(r'pnc-visits', PNCVisitViewSet, basename='pnc-visit')
router.register(r'pnc-newborn-assessments', PNCNewbornAssessmentViewSet, basename='pnc-newborn-assessment')
router.register(r'deliveries', DeliveryViewSet, basename='delivery')

urlpatterns = [
    path('appointment-for-anc/', AppointmentForANCView.as_view(), name='unified-appointment-anc'),
    path('appointment-for-pnc/', AppointmentForPNCView.as_view(), name='unified-appointment-pnc'),
    path('follow-ups/upcoming/', UpcomingMaternalFollowUpsView.as_view(), name='upcoming-maternal-follow-ups'),
    path('', include(router.urls)),
]
