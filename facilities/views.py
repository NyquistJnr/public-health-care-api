# facilities/views.py
from rest_framework import viewsets
from drf_spectacular.utils import extend_schema, OpenApiParameter
from .models import Facility
from .serializers import FacilitySerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from core.serializers import StatusUpdateSerializer, EmptyStatsSerializer
from django.utils import timezone

@extend_schema(tags=["Facility Management"])
class FacilityViewSet(viewsets.ModelViewSet):
    queryset = Facility.objects.all().order_by('-created_at')
    serializer_class = FacilitySerializer
    http_method_names = ['get', 'post', 'patch', 'delete'] 
    # permission_classes = [HasRequiredPermission]
    


    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        instance.delete(deleted_by=self.request.user)

    @extend_schema(
        parameters=[
            OpenApiParameter(name='is_active', description='Filter by active status (true/false)', required=False, type=str)
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        
        is_active_param = self.request.query_params.get('is_active')
        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ['true', '1', 't', 'y', 'yes']
            qs = qs.filter(is_active=is_active_bool)
            
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
