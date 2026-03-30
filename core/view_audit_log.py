# core/view_audit_log.py
from .models import AuditLog
from .serializers import AuditLogSerializer
from rest_framework import generics
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db.models import Q

@extend_schema(
    tags=["System Administration"], 
    summary="Fetch and Filter System Audit Logs",
    parameters=[
        OpenApiParameter(name='action', description='Filter by action (e.g., CREATE, UPDATE, SUSPEND)', required=False, type=str),
        OpenApiParameter(name='module', description='Filter by module (e.g., Core - User)', required=False, type=str),
        OpenApiParameter(name='search', description='Search by actor name or endpoint', required=False, type=str),
        OpenApiParameter(name='start_date', description='Filter by start date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter by end date (YYYY-MM-DD)', required=False, type=str),
    ]
)
class AuditLogListView(generics.ListAPIView):
    serializer_class = AuditLogSerializer
    # permission_classes = [HasRequiredPermission]


    def get_queryset(self):
        user = self.request.user
        
        qs = AuditLog.objects.all()
        # if user.role == 'ADMIN':
        #     qs = AuditLog.objects.all()
        # elif user.role == 'FACILITY_IT_ADMIN':
        #     qs = AuditLog.objects.filter(facility=user.facility)
        # else:
        #     raise PermissionDenied("You do not have security clearance to view audit logs.")

        action = self.request.query_params.get('action')
        if action:
            qs = qs.filter(action__iexact=action)

        module = self.request.query_params.get('module')
        if module:
            qs = qs.filter(module__icontains=module)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(actor_name__icontains=search) |
                Q(endpoint__icontains=search)
            )

        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            qs = qs.filter(timestamp__gte=start_date)
        if end_date:
            qs = qs.filter(timestamp__lte=end_date)

        return qs

@extend_schema(
    tags=["Notifications"], 
    summary="Fetch Notifications (User Actions) specific to user's role",
    parameters=[
        OpenApiParameter(name='action', description='Filter by action (e.g., CREATE, UPDATE, SUSPEND)', required=False, type=str),
        OpenApiParameter(name='module', description='Filter by module (e.g., Core - User)', required=False, type=str),
        OpenApiParameter(name='search', description='Search by actor name or endpoint', required=False, type=str),
        OpenApiParameter(name='start_date', description='Filter by start date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter by end date (YYYY-MM-DD)', required=False, type=str),
    ]
)
class NotificationListView(generics.ListAPIView):
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        user = self.request.user
        
        if not user.is_authenticated:
            return AuditLog.objects.none()

        if user.role == 'ADMIN':
            qs = AuditLog.objects.all()
        elif user.role == 'FACILITY_IT_ADMIN':
            qs = AuditLog.objects.filter(facility=user.facility)
        else:
            qs = AuditLog.objects.filter(actor=user)

        action = self.request.query_params.get('action')
        if action:
            qs = qs.filter(action__iexact=action)

        module = self.request.query_params.get('module')
        if module:
            qs = qs.filter(module__icontains=module)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(actor_name__icontains=search) |
                Q(endpoint__icontains=search)
            )

        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            qs = qs.filter(timestamp__gte=start_date)
        if end_date:
            qs = qs.filter(timestamp__lte=end_date)

        return qs

