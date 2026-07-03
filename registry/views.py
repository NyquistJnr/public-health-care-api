# registry/views.py
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsStateAdmin
from core.pagination import StandardResultsSetPagination
from .models import Disease, SystemThreshold
from .serializers import DiseaseSerializer, SystemThresholdSerializer


class IsSuperUser(permissions.BasePermission):
    """Restricts access to Django superusers - these thresholds are global/cross-tenant."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


@extend_schema(
    tags=["Disease Registry"],
    summary="List Diseases (Global Registry)",
    parameters=[
        OpenApiParameter(name='severity', description='Filter by severity (CRITICAL, MODERATE, LOW)', required=False, type=str),
        OpenApiParameter(name='search', description='Search by disease name', required=False, type=str),
    ]
)
class DiseaseListView(generics.ListAPIView):
    serializer_class = DiseaseSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = Disease.objects.filter(is_active=True)

        severity = self.request.query_params.get('severity')
        if severity:
            qs = qs.filter(severity__iexact=severity)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(name__icontains=search))

        return qs


@extend_schema(
    tags=["Disease Registry"],
    summary="Get or Update the Global System Thresholds",
    description=(
        "GET is available to any State Admin. PATCH is restricted to Django superusers, "
        "since these thresholds are global and apply across every state."
    ),
    responses=SystemThresholdSerializer
)
class SystemThresholdView(APIView):
    serializer_class = SystemThresholdSerializer

    def get_permissions(self):
        if self.request.method == 'PATCH':
            return [IsSuperUser()]
        return [IsStateAdmin()]

    def get(self, request):
        threshold = SystemThreshold.get_solo()
        return Response(SystemThresholdSerializer(threshold).data)

    def patch(self, request):
        threshold = SystemThreshold.get_solo()
        serializer = SystemThresholdSerializer(threshold, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
