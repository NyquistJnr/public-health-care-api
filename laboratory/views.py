# laboratory/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db.models import Q, Sum

from .models import LabRequest, LabTest
from inventory.models import InventoryItem, ItemBatch, InventoryTransaction
from .serializers import (
    LabRequestReadSerializer, LabRequestCreateSerializer, 
    LabTestItemSerializer, LabResultSubmitSerializer, LabTestStatsResponseSerializer,
    LabRequestStatsResponseSerializer,
    OverallLabStatsResponseSerializer
)

@extend_schema(tags=["Laboratory"])
class LabRequestViewSet(viewsets.ModelViewSet):
    queryset = LabRequest.objects.none()

    def get_serializer_class(self):
        if self.action == 'create':
            return LabRequestCreateSerializer
        return LabRequestReadSerializer

    @extend_schema(
        summary="List & Filter Lab Requests (Orders)",
        parameters=[
            OpenApiParameter(name='patient_id', description='Filter by Patient UUID', required=False, type=str),
            OpenApiParameter(name='appointment_id', description='Filter by Appointment UUID', required=False, type=str),
            OpenApiParameter(name='status', description='PENDING, PARTIAL, COMPLETED, CANCELLED', required=False, type=str),
            OpenApiParameter(name='priority', description='NORMAL, URGENT, STAT', required=False, type=str),
            OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='search', description='Search by Patient Name or Test Name', required=False, type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = LabRequest.objects.filter(patient__facility=self.request.user.facility)
        
        patient_id = self.request.query_params.get('patient_id')
        appt_id = self.request.query_params.get('appointment_id')
        req_status = self.request.query_params.get('status')
        priority = self.request.query_params.get('priority')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        search = self.request.query_params.get('search')

        if patient_id: qs = qs.filter(patient__id=patient_id)
        if appt_id: qs = qs.filter(appointment__id=appt_id)
        if req_status: qs = qs.filter(status=req_status.upper())
        if priority: qs = qs.filter(priority=priority.upper())
        if start_date: qs = qs.filter(created_at__date__gte=start_date)
        if end_date: qs = qs.filter(created_at__date__lte=end_date)
            
        if search:
            qs = qs.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search) |
                Q(tests__test_name__icontains=search)
            ).distinct()

        return qs.order_by('-created_at')


@extend_schema(tags=["Laboratory"])
class LabTestViewSet(viewsets.ModelViewSet):
    queryset = LabTest.objects.none()
    serializer_class = LabTestItemSerializer
    http_method_names = ['get', 'patch'] 

    @extend_schema(
        summary="List & Filter Individual Tests (The Lab Queue)",
        parameters=[
            OpenApiParameter(name='lab_request_id', description='Filter tests by a specific Lab Request (Order) UUID', required=False, type=str),
            OpenApiParameter(name='test_status', description='PENDING, SAMPLE_COLLECTED, PROCESSING, RESULT_READY', required=False, type=str),
            OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
            OpenApiParameter(name='search', description='Search by Patient Name or Test Name', required=False, type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = LabTest.objects.filter(lab_request__patient__facility=self.request.user.facility)
        
        lab_request_id = self.request.query_params.get('lab_request_id')
        test_status = self.request.query_params.get('test_status')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        search = self.request.query_params.get('search')
        
        if lab_request_id: qs = qs.filter(lab_request__id=lab_request_id)
        if test_status: qs = qs.filter(test_status=test_status.upper())
        if start_date: qs = qs.filter(created_at__date__gte=start_date)
        if end_date: qs = qs.filter(created_at__date__lte=end_date)
            
        if search:
            qs = qs.filter(
                Q(lab_request__patient__first_name__icontains=search) |
                Q(lab_request__patient__last_name__icontains=search) |
                Q(test_name__icontains=search)
            )
            
        return qs.order_by('-created_at')

    @extend_schema(summary="Submit Lab Result & Auto-Deduct Inventory", request=LabResultSubmitSerializer)
    @action(detail=True, methods=['patch'], url_path='submit-result')
    @transaction.atomic
    def submit_result(self, request, pk=None):
        test = self.get_object()
        
        if test.test_status == 'RESULT_READY':
            return Response({"detail": "This test result has already been submitted."}, status=status.HTTP_400_BAD_REQUEST)

        if test.linked_item and not test.inventory_deducted:
            today = timezone.now().date()
            active_batches = ItemBatch.objects.filter(
                item=test.linked_item,
                is_active=True,
                remaining_quantity__gt=0
            ).filter(
                Q(expiry_date__gte=today) | Q(expiry_date__isnull=True)
            ).select_for_update().order_by('expiry_date')

            if sum(b.remaining_quantity for b in active_batches) < 1:
                return Response(
                    {"detail": f"Cannot submit result. {test.linked_item.name} is completely out of stock."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            batch = active_batches.first()
            batch.remaining_quantity -= 1
            batch.save(update_fields=['remaining_quantity', 'updated_at'])

            InventoryTransaction.objects.create(
                batch=batch, transaction_type='DISPENSE', quantity=-1, performed_by=request.user
            )
            test.inventory_deducted = True

        serializer = LabResultSubmitSerializer(test, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        updated_test = serializer.save(
            test_status='RESULT_READY',
            result_entered_by=request.user,
            result_date=timezone.now(),
            updated_by=request.user
        )
        
        updated_test.check_and_update_parent_status()

        return Response({
            "detail": "Result submitted successfully.",
            "parent_request_status": updated_test.lab_request.status
        }, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Laboratory"],
    summary="Get Lab Test Statistics",
    parameters=[
        OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
    ]
)
class LabTestStatsView(APIView):
    serializer_class = LabTestStatsResponseSerializer
    def get(self, request):
        qs = LabTest.objects.filter(lab_request__patient__facility=request.user.facility)
        
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date: qs = qs.filter(created_at__date__gte=start_date)
        if end_date: qs = qs.filter(created_at__date__lte=end_date)

        return Response({
            "pending_tests": qs.filter(test_status__in=['PENDING', 'SAMPLE_COLLECTED']).count(),
            "in_progress": qs.filter(test_status='PROCESSING').count(),
            "completed": qs.filter(test_status='RESULT_READY').count()
        })


@extend_schema(
    tags=["Laboratory"],
    summary="Get Lab Request (Order) Statistics",
    parameters=[
        OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
    ]
)
class LabRequestStatsView(APIView):
    serializer_class = LabRequestStatsResponseSerializer
    def get(self, request):
        qs = LabRequest.objects.filter(patient__facility=request.user.facility)
        
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date: qs = qs.filter(created_at__date__gte=start_date)
        if end_date: qs = qs.filter(created_at__date__lte=end_date)

        return Response({
            "pending_requests": qs.filter(status='PENDING').count(),
            "in_progress": qs.filter(status='PARTIAL').count(),
            "completed": qs.filter(status='COMPLETED').count()
        })


@extend_schema(
    tags=["Laboratory"],
    summary="Get Overall Lab Facility Stats & Inventory Alerts",
    parameters=[
        OpenApiParameter(name='start_date', description='Filter from date (YYYY-MM-DD)', required=False, type=str),
        OpenApiParameter(name='end_date', description='Filter to date (YYYY-MM-DD)', required=False, type=str),
    ]
)
class OverallLabStatsView(APIView):
    serializer_class = OverallLabStatsResponseSerializer
    def get(self, request):
        qs = LabRequest.objects.filter(patient__facility=request.user.facility)
        
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date: qs = qs.filter(created_at__date__gte=start_date)
        if end_date: qs = qs.filter(created_at__date__lte=end_date)

        pending = qs.filter(status='PENDING').count()
        in_progress = qs.filter(status='PARTIAL').count()
        completed = qs.filter(status='COMPLETED').count()

        lab_items = InventoryItem.objects.filter(
            facility=request.user.facility,
            inventory_category__in=['LAB_EQUIPMENT', 'CONSUMABLE']
        )
        today = timezone.now().date()
        inventory_alerts = []

        for item in lab_items:
            stock = item.batches.filter(
                is_active=True
            ).filter(
                Q(expiry_date__gte=today) | Q(expiry_date__isnull=True)
            ).aggregate(total=Sum('remaining_quantity'))['total'] or 0

            if stock <= item.global_threshold:
                inventory_alerts.append({
                    "item_id": str(item.id),
                    "item_name": item.name,
                    "category": item.get_inventory_category_display(),
                    "current_stock": stock,
                    "threshold": item.global_threshold,
                    "unit": item.item_type
                })

        return Response({
            "pending_lab_requests": pending,
            "in_progress": in_progress,
            "completed": completed,
            "inventory_alert_count": len(inventory_alerts),
            "inventory_alerts": inventory_alerts
        })
