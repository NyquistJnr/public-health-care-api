from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter
from .models import Department
from core.models import User
from .serializers import (
    DepartmentSerializer, 
    DepartmentDetailSerializer, 
    DepartmentMemberUpdateSerializer
)

@extend_schema(tags=["Facility Departments"])
class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.none()

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return DepartmentDetailSerializer
        return DepartmentSerializer

    @extend_schema(
        summary="List & Filter Facility Departments",
        parameters=[
            OpenApiParameter(name='search', description='Search by department name', required=False, type=str),
            OpenApiParameter(name='is_active', description='Filter by active status (true/false)', required=False, type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = Department.objects.filter(facility=self.request.user.facility)
        
        search = self.request.query_params.get('search')
        is_active_param = self.request.query_params.get('is_active')

        if search:
            qs = qs.filter(name__icontains=search)
            
        if is_active_param is not None:
            is_active_bool = is_active_param.lower() in ['true', '1', 't', 'y', 'yes']
            qs = qs.filter(is_active=is_active_bool)

        return qs.order_by('name')

    def perform_create(self, serializer):
        serializer.save(facility=self.request.user.facility, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @extend_schema(
        summary="Add Staff Members to Department", 
        request=DepartmentMemberUpdateSerializer
    )
    @action(detail=True, methods=['post'], url_path='add-members')
    def add_members(self, request, pk=None):
        department = self.get_object()
        serializer = DepartmentMemberUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_ids = serializer.validated_data['user_ids']
        
        valid_staff = User.objects.filter(
            id__in=user_ids,
            facility=request.user.facility
        ).exclude(role='PATIENT')

        if not valid_staff.exists():
            return Response(
                {"detail": "No valid staff members found for the provided IDs in this facility."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        department.members.add(*valid_staff)

        return Response({
            "detail": f"Successfully added {valid_staff.count()} staff member(s) to {department.name}."
        }, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Remove Staff Members from Department", 
        request=DepartmentMemberUpdateSerializer
    )
    @action(detail=True, methods=['post'], url_path='remove-members')
    def remove_members(self, request, pk=None):
        department = self.get_object()
        serializer = DepartmentMemberUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_ids = serializer.validated_data['user_ids']
        
        staff_to_remove = User.objects.filter(id__in=user_ids)
        department.members.remove(*staff_to_remove)

        return Response({
            "detail": "Staff member(s) successfully removed from the department."
        }, status=status.HTTP_200_OK)
