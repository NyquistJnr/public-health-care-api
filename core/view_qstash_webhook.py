# core/view_qstash_webhook.py

from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.core.mail import send_mail
from django_tenants.utils import schema_context
from qstash import Receiver
import json
from referrals.models import Referral
from referrals.services import compile_and_send_external_referral
from drf_spectacular.utils import extend_schema

@extend_schema(exclude=True)
class QStashWebhookView(APIView):
    """
    Catches async tasks from Upstash. Secured via cryptographic signature.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        signature = request.headers.get("Upstash-Signature")
        if not signature:
            return Response({"error": "Missing signature"}, status=status.HTTP_401_UNAUTHORIZED)

        receiver = Receiver(
            current_signing_key=settings.QSTASH_CURRENT_SIGNING_KEY,
            next_signing_key=settings.QSTASH_NEXT_SIGNING_KEY,
        )

        try:
            receiver.verify(
                body=request.body.decode('utf-8'),
                signature=signature,
                url=f"https://{request.get_host()}/api/v1/system/qstash-webhook/"
            )
        except Exception as e:
            return Response({"error": "Invalid signature", "details": str(e)}, status=status.HTTP_401_UNAUTHORIZED)

        payload = json.loads(request.body)
        task_type = payload.get("task_type")
        schema_name = payload.get("schema_name")

        if not schema_name:
            return Response({"error": "Missing schema_name in payload"}, status=status.HTTP_400_BAD_REQUEST)
        
        with schema_context(schema_name):

            if task_type == "PATIENT_REMINDER":
                patient_email = payload.get("patient_email")
                message = payload.get("message")
                tenant = payload.get("tenant_domain")

                with schema_context(schema_name):
                    if patient_email:
                        send_mail(
                            subject="Medical Appointment Reminder",
                            message=f"Hello,\n\nThis is a reminder from {tenant}:\n\n{message}\n\nPlease visit the clinic at your earliest convenience.",
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[patient_email],
                            fail_silently=False,
                        )

                return Response({"status": "Reminder sent successfully"}, status=status.HTTP_200_OK)

            if task_type == "EXTERNAL_REFERRAL":
                ref_id = payload.get("referral_id")
                req_host = payload.get("request_host")

                with schema_context(schema_name):
                    try:
                        referral = Referral.objects.get(id=ref_id)
                        compile_and_send_external_referral(referral, req_host)
                        return Response({"status": "Referral email dispatched successfully"}, status=status.HTTP_200_OK)
                    except Referral.DoesNotExist:
                        return Response({"error": "Referral not found"}, status=status.HTTP_404_NOT_FOUND)


            if task_type == "AUTH_EMAIL":
                email = payload.get("email")
                ctx = payload.get("context")
                
                subject = ctx.get("subject")
                message = ctx.get("message")
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
                return Response({"status": "Auth email sent"}, status=200)

        return Response({"status": "Unknown task type ignored"}, status=status.HTTP_200_OK)
