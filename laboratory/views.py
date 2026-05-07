# laboratory/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db.models import Q
from .models import LabRequest, LabTest
from .serializers import (
    LabRequestReadSerializer, LabRequestCreateSerializer, 
    LabTestItemSerializer, LabResultSubmitSerializer
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
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = LabRequest.objects.filter(patient__facility=self.request.user.facility)
        
        patient_id = self.request.query_params.get('patient_id')
        appt_id = self.request.query_params.get('appointment_id')
        req_status = self.request.query_params.get('status')

        if patient_id:
            qs = qs.filter(patient__id=patient_id)
        if appt_id:
            qs = qs.filter(appointment__id=appt_id)
        if req_status:
            qs = qs.filter(status=req_status.upper())

        return qs.order_by('-created_at')


@extend_schema(tags=["Laboratory"])
class LabTestViewSet(viewsets.ModelViewSet):
    """Used primarily by Lab Technicians to manage individual tests"""
    queryset = LabTest.objects.none()
    serializer_class = LabTestItemSerializer
    http_method_names = ['get', 'patch']

    @extend_schema(
        summary="List & Filter Individual Tests (The Lab Queue)",
        parameters=[
            OpenApiParameter(name='lab_request_id', description='Filter tests by a specific Lab Request (Order) UUID', required=False, type=str),
            OpenApiParameter(name='test_status', description='PENDING, SAMPLE_COLLECTED, PROCESSING, RESULT_READY', required=False, type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = LabTest.objects.filter(lab_request__patient__facility=self.request.user.facility)
        
        lab_request_id = self.request.query_params.get('lab_request_id')
        test_status = self.request.query_params.get('test_status')
        
        if lab_request_id:
            qs = qs.filter(lab_request__id=lab_request_id)
            
        if test_status:
            qs = qs.filter(test_status=test_status.upper())
            
        return qs.order_by('-created_at')

    @extend_schema(summary="Submit Lab Result", request=LabResultSubmitSerializer)
    @action(detail=True, methods=['patch'], url_path='submit-result')
    def submit_result(self, request, pk=None):
        test = self.get_object()
        
        if test.test_status == 'RESULT_READY':
            return Response({"detail": "This test result has already been submitted."}, status=status.HTTP_400_BAD_REQUEST)

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
