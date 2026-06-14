from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DepartmentViewSet, SpecificFacilityDepartmentListView

router = DefaultRouter()
router.register(r'', DepartmentViewSet, basename='department')

urlpatterns = [
    path('facilities/<uuid:facility_id>/', SpecificFacilityDepartmentListView.as_view(), name='specific-facility-departments'),
    path('', include(router.urls)),
]
