# core/view_audit_log.py
from .models import AuditLog, NotificationReadStatus
from .serializers import AuditLogSerializer
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db.models import Q, Exists, OuterRef
from django.shortcuts import get_object_or_404

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

        qs = qs.annotate(
            is_read=Exists(
                NotificationReadStatus.objects.filter(
                    audit_log=OuterRef('pk'),
                    user=user
                )
            )
        )

        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        # Calculate stats (do this before paginate_queryset to use the full queryset)
        total_read = queryset.filter(is_read=True).count()
        total_unread = queryset.filter(is_read=False).count()
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data['stats'] = {
                'read': total_read,
                'unread': total_unread
            }
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'stats': {
                'read': total_read,
                'unread': total_unread
            },
            'results': serializer.data
        })

@extend_schema(
    tags=["Notifications"], 
    summary="Mark a Notification as Read",
)
class NotificationMarkReadView(APIView):
    def patch(self, request, pk):
        audit_log = get_object_or_404(AuditLog, pk=pk)
        NotificationReadStatus.objects.get_or_create(
            audit_log=audit_log,
            user=request.user
        )
        return Response({"status": "success", "is_read": True})
