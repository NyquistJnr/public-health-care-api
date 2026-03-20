# facilities/views.py
from rest_framework import viewsets
from drf_spectacular.utils import extend_schema
from core.permissions import HasRequiredPermission
from .models import Facility
from .serializers import FacilitySerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from core.serializers import StatusUpdateSerializer, EmptyStatsSerializer

@extend_schema(tags=["Facility Management"])
class FacilityViewSet(viewsets.ModelViewSet):
    queryset = Facility.objects.filter(is_active=True).order_by('-created_at')
    serializer_class = FacilitySerializer
    http_method_names = ['get', 'post', 'patch', 'delete'] 
    
    permission_classes = [HasRequiredPermission]
    
    @property
    def required_permissions(self):
        if self.action == 'create':
            return ['facilities.add_facility']
        elif self.action in ['update', 'partial_update']:
            return ['facilities.change_facility']
        elif self.action == 'destroy':
            return ['facilities.delete_facility']
            
        return ['facilities.view_facility']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        instance.delete(deleted_by=self.request.user)

@extend_schema(tags=["Facility Management"], summary="Suspend or Activate an Entire Facility", request=StatusUpdateSerializer)
class FacilityStatusToggleView(APIView):
    permission_classes = [HasRequiredPermission]
    serializer_class = StatusUpdateSerializer
    
    @property
    def required_permissions(self): 
        return ['facilities.change_facility']

    def patch(self, request, facility_id):
        serializer = StatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            facility = Facility.objects.get(id=facility_id)
            facility.is_active = serializer.validated_data['is_active']
            facility.save(update_fields=['is_active', 'updated_at'])

            status_text = "activated" if facility.is_active else "suspended"
            return Response({"detail": f"Facility '{facility.name}' has been {status_text}. Staff login access has been updated."})

        except Facility.DoesNotExist:
            return Response({"detail": "Facility not found."}, status=status.HTTP_404_NOT_FOUND)

@extend_schema(tags=["Facility Management"], summary="Get State-Wide Facility Statistics")
class StateFacilityStatsView(APIView):
    permission_classes = [HasRequiredPermission]
    serializer_class = EmptyStatsSerializer
    
    @property
    def required_permissions(self): 
        return ['facilities.view_facility']

    def get(self, request):
        return Response({
            "total_facilities": Facility.objects.count(),
            "active_facilities": Facility.objects.filter(is_active=True).count(),
            "suspended_facilities": Facility.objects.filter(is_active=False).count()
        })
