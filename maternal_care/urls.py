# maternal_care/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    MaternalCareEpisodeViewSet, ANCVisitViewSet, 
    PNCVisitViewSet, PNCNewbornAssessmentViewSet,
    MaternalScheduleRuleViewSet
)

router = DefaultRouter()
router.register(r'global-rules', MaternalScheduleRuleViewSet, basename='maternal-schedule-rule')
router.register(r'episodes', MaternalCareEpisodeViewSet, basename='maternal-episode')
router.register(r'anc-visits', ANCVisitViewSet, basename='anc-visit')
router.register(r'pnc-visits', PNCVisitViewSet, basename='pnc-visit')
router.register(r'pnc-newborn-assessments', PNCNewbornAssessmentViewSet, basename='pnc-newborn-assessment')

urlpatterns = [
    path('', include(router.urls)),
]
