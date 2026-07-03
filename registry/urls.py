# registry/urls.py
from django.urls import path

from .views import DiseaseListView, SystemThresholdView

urlpatterns = [
    path('diseases/', DiseaseListView.as_view(), name='disease_list'),
    path('thresholds/', SystemThresholdView.as_view(), name='system_thresholds'),
]
