from qstash import QStash
from django.conf import settings
from django.db import connection
from datetime import date
import datetime

def schedule_patient_reminder(patient_id: str, patient_email: str, message: str, due_date: date, request_host: str):
    """
    Pushes a task to QStash to be executed on a specific future date.
    """
    client = QStash(settings.QSTASH_TOKEN)
    
    dt = datetime.datetime.combine(due_date, datetime.time(8, 0))
    not_before_timestamp = int(dt.timestamp())

    webhook_url = f"https://{request_host}/api/v1/system/qstash-webhook/"

    res = client.message.publish_json(
        url=webhook_url,
        body={
            "task_type": "PATIENT_REMINDER",
            "patient_id": patient_id,
            "patient_email": patient_email,
            "message": message,
            "tenant_domain": request_host,
            "schema_name": connection.schema_name,
        },
        not_before=not_before_timestamp
    )
    
    return res.message_id

def dispatch_external_referral(referral_id: str, request_host: str):
    """
    Pushes an immediate task to QStash to process and email an external referral in the background.
    """
    client = QStash(settings.QSTASH_TOKEN)
    
    base_url = getattr(settings, 'WEBHOOK_BASE_URL', None) or f"https://{request_host}"
    
    webhook_url = f"{base_url}/api/v1/system/qstash-webhook/"

    res = client.message.publish_json(
        url=webhook_url,
        body={
            "task_type": "EXTERNAL_REFERRAL",
            "referral_id": str(referral_id),
            "request_host": base_url.replace("https://", "").replace("http://", ""),
            "schema_name": connection.schema_name,
        }
    )
    
    return res.message_id
