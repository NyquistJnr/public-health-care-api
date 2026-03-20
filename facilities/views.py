# facilities/views.py
from rest_framework import viewsets
from drf_spectacular.utils import extend_schema
from core.permissions import HasRequiredPermission
from .models import Facility
from .serializers import FacilitySerializer

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
