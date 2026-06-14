from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter
from .models import Department
from core.models import User
from .serializers import (
    DepartmentSerializer, 
    DepartmentMemberListSerializer, 
    DepartmentMemberUpdateSerializer,
    FacilityDepartmentListSerializer
)

@extend_schema(tags=["Departments"])
class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.none()
    serializer_class = DepartmentSerializer

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
        summary="Get Paginated Department Members", 
        responses=DepartmentMemberListSerializer(many=True),
        parameters=[
            OpenApiParameter(name='search', description='Search staff by name or ID', required=False, type=str),
        ]
    )
    @action(detail=True, methods=['get'], url_path='members')
    def get_members(self, request, pk=None):
        department = self.get_object()
        
        query = Q(department_memberships=department)
        if department.head_id:
            query |= Q(id=department.head_id)
            
        members_qs = User.objects.filter(query).distinct()

        search = request.query_params.get('search')
        if search:
            members_qs = members_qs.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(staff_id__icontains=search)
            )

        members_qs = members_qs.order_by('first_name', 'last_name')
        page = self.paginate_queryset(members_qs)
    
        serializer_context = self.get_serializer_context()
        serializer_context['head_id'] = department.head_id

        if page is not None:
            serializer = DepartmentMemberListSerializer(page, many=True, context=serializer_context)
            return self.get_paginated_response(serializer.data)

        serializer = DepartmentMemberListSerializer(members_qs, many=True, context=serializer_context)
        return Response(serializer.data)


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

@extend_schema(
    tags=["Facility Departments"],
    summary="Get All Departments for a Specific Facility",
    parameters=[
        OpenApiParameter(name='search', description='Search by department name', required=False, type=str),
    ]
)
class SpecificFacilityDepartmentListView(generics.ListAPIView):
    serializer_class = FacilityDepartmentListSerializer

    def get_queryset(self):
        facility_id = self.kwargs.get('facility_id')
        
        qs = Department.objects.filter(
            facility_id=facility_id
        ).select_related('facility', 'head')
        
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(name__icontains=search)
            
        return qs.order_by('name')
