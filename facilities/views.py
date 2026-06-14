# facilities/views.py
from rest_framework import viewsets
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db.models import Q, Count
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import connection

from .models import Facility
from .serializers import FacilitySerializer
from core.serializers import StatusUpdateSerializer, EmptyStatsSerializer


@extend_schema(tags=["Facility Management"])
class FacilityViewSet(viewsets.ModelViewSet):
    queryset = Facility.objects.all().order_by('-created_at')
    serializer_class = FacilitySerializer
    http_method_names = ['get', 'post', 'patch', 'delete'] 

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        instance.delete(deleted_by=self.request.user)

    @extend_schema(
        summary="List & Filter Facilities",
        parameters=[
            OpenApiParameter(name='is_active', description='Filter by active status (true/false)', required=False, type=str),
            OpenApiParameter(name='search', description='Search by facility name, code, or email', required=False, type=str),
            OpenApiParameter(name='state', description='Filter by state name', required=False, type=str),
            OpenApiParameter(name='lga', description='Filter by LGA', required=False, type=str),
            OpenApiParameter(name='ward', description='Filter by Ward', required=False, type=str)
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        
        is_active_param = self.request.query_params.get('is_active')
        search = self.request.query_params.get('search')
        state = self.request.query_params.get('state')
        lga = self.request.query_params.get('lga')
        ward = self.request.query_params.get('ward')

        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ['true', '1', 't', 'y', 'yes']
            qs = qs.filter(is_active=is_active_bool)

        if state:
            current_state = connection.tenant.name if hasattr(connection, 'tenant') else ""
            if state.lower() != current_state.lower():
                return qs.none()

        if lga:
            qs = qs.filter(lga__icontains=lga)
        if ward:
            qs = qs.filter(ward__icontains=ward)

        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search) |
                Q(manager_email__icontains=search) |
                Q(lga__icontains=search)
            )
            
        qs = qs.annotate(
            annotated_staff_count=Count(
                'staff_members', 
                filter=~Q(staff_members__role='PATIENT') & Q(staff_members__is_active=True), 
                distinct=True
            ),
            annotated_patient_count=Count(
                'staff_members', 
                filter=Q(staff_members__role='PATIENT') & Q(staff_members__is_active=True), 
                distinct=True
            ),
            annotated_department_count=Count(
                'departments', 
                filter=Q(departments__is_active=True), 
                distinct=True
            )
        )
            
        return qs

@extend_schema(tags=["Facility Management"], summary="Suspend or Activate an Entire Facility", request=StatusUpdateSerializer)
class FacilityStatusToggleView(APIView):
    # permission_classes = [HasRequiredPermission]
    serializer_class = StatusUpdateSerializer

    def patch(self, request, facility_id):
        serializer = StatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            facility = Facility.objects.get(id=facility_id)
            is_active = serializer.validated_data['is_active']
            facility.is_active = is_active
            facility.suspended_at = None if is_active else timezone.now()
            
            facility.save(update_fields=['is_active', 'suspended_at', 'updated_at'])

            status_text = "activated" if facility.is_active else "suspended"
            return Response({"detail": f"Facility '{facility.name}' has been {status_text}. Staff login access has been updated."})

        except Facility.DoesNotExist:
            return Response({"detail": "Facility not found."}, status=status.HTTP_404_NOT_FOUND)

@extend_schema(tags=["Facility Management"], summary="Get State-Wide Facility Statistics")
class StateFacilityStatsView(APIView):
    # permission_classes = [HasRequiredPermission]
    serializer_class = EmptyStatsSerializer

    def get(self, request):
        return Response({
            "total_facilities": Facility.objects.count(),
            "active_facilities": Facility.objects.filter(is_active=True).count(),
            "suspended_facilities": Facility.objects.filter(is_active=False).count()
        })
