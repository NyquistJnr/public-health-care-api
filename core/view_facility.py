# core/views.py
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied
from drf_spectacular.utils import extend_schema, OpenApiParameter
from .serializers import FacilityUserListSerializer, PatientCreateSerializer
from rest_framework import generics
from drf_spectacular.utils import extend_schema
from .models import User
from core.permissions import HasRequiredPermission

@extend_schema(
    tags=["Facility Management"], 
    summary="List Facility Users (Staff & Patients)",
    parameters=[
        OpenApiParameter(name='search', description='Search by name, email, or phone', required=False, type=str),
        OpenApiParameter(name='role', description='Filter by role (DOCTOR, NURSE) or use "STAFF" for all employees', required=False, type=str),
        OpenApiParameter(name='start_date', description='Filter by start date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter by end date (YYYY-MM-DD)', required=False, type=str),
    ]
)
class FacilityUserListView(generics.ListAPIView):
    serializer_class = FacilityUserListSerializer
    permission_classes = [HasRequiredPermission]

    @property
    def required_permissions(self):
        return ['core.view_user'] 

    def get_queryset(self):
        requester = self.request.user
        
        qs = User.objects.filter(facility=requester.facility)
        if requester.role in ['FACILITY_IT_ADMIN', 'ADMIN']:
            qs = qs.exclude(role='PATIENT')

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone_number__icontains=search)
            )

        role = self.request.query_params.get('role')
        if role:
            if role.upper() == 'STAFF':
                qs = qs.exclude(role='PATIENT')
            else:
                qs = qs.filter(role=role.upper())

        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            qs = qs.filter(created_at__gte=start_date)
        if end_date:
            qs = qs.filter(created_at__lte=end_date)

        return qs.order_by('-created_at')


@extend_schema(tags=["Patient Management"], summary="Register New Patient")
class PatientCreateView(generics.CreateAPIView):
    serializer_class = PatientCreateSerializer
    permission_classes = [HasRequiredPermission]

    @property
    def required_permissions(self):
        return ['core.add_user']

    def perform_create(self, serializer):
        if self.request.user.role not in ['DOCTOR', 'NURSE']:
            raise PermissionDenied("Only clinical staff (Doctors and Nurses) can register patients.")
        
        serializer.save(
            created_by=self.request.user, 
            facility=self.request.user.facility
        )
