from django.core.mail import send_mail
from django.core.signing import TimestampSigner
from django.conf import settings
from .models import Referral

def compile_and_send_external_referral(referral: Referral, request_host: str):
    patient = referral.patient
    appointment = referral.appointment
    
    signer = TimestampSigner()
    
    token_accept = signer.sign(f"{referral.id}:ACCEPTED")
    token_reject = signer.sign(f"{referral.id}:REJECTED")

    base_url = f"https://{request_host}" if request_host else getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    
    accept_link = f"{base_url}/api/v1/referrals/external-action/?token={token_accept}"
    reject_link = f"{base_url}/api/v1/referrals/external-action/?token={token_reject}"

    consultation = getattr(appointment, 'consultation', None)
    vitals = appointment.vitals.first()
    
    medical_text = f"--- PATIENT DEMOGRAPHICS ---\n"
    medical_text += f"Name: {patient.get_full_name()} (ID: {patient.patient_profile.patient_id})\n"
    medical_text += f"Age: {patient.patient_profile.age_group} | Sex: {patient.patient_profile.get_sex_display()}\n\n"

    if vitals:
        medical_text += f"--- VITALS ---\n"
        medical_text += f"BP: {vitals.blood_pressure or 'N/A'} | Temp: {vitals.temperature or 'N/A'}°C | Pulse: {vitals.pulse_rate or 'N/A'} bpm\n\n"

    if consultation:
        medical_text += f"--- CONSULTATION NOTES ---\n"
        medical_text += f"Chief Complaint: {consultation.chief_complaint}\n"
        medical_text += f"Primary Diagnosis: {consultation.primary_diagnosis}\n"
        medical_text += f"Treatment Plan: {consultation.treatment_plan}\n\n"

    hardcopy_notice = ""
    if referral.mode_of_referral == 'HARDCOPY':
        hardcopy_notice = "*** NOTE: The physical hardcopy of this referral has been given to the patient to present upon arrival. ***\n\n"
    elif referral.mode_of_referral == 'SOFTCOPY':
        hardcopy_notice = "*** NOTE: This is a digital softcopy referral. No physical paperwork will be provided by the patient. ***\n\n"

    final_body = (
        f"Dear Colleague,\n\n"
        f"You are receiving a {referral.get_referral_type_display()} referral from {referral.referring_facility.name}.\n\n"
        f"{hardcopy_notice}"
        f"Subject: {referral.email_subject or 'Patient Referral'}\n"
        f"Doctor's Note: {referral.email_body or 'Please see attached clinical summary.'}\n\n"
        f"Reason for Referral: {referral.reason_for_referral}\n"
        f"Clinical Summary: {referral.clinical_summary or 'N/A'}\n\n"
        f"{medical_text}"
        f"Referred by: {referral.referred_by.get_full_name()} ({referral.referred_by.email})\n\n"
        f"=========================================\n"
        f"PLEASE UPDATE THE REFERRAL STATUS BELOW:\n"
        f"=========================================\n"
        f"To ACCEPT, click here: {accept_link}\n\n"
        f"To REJECT, click here: {reject_link}\n"
    )

    html_body = final_body.replace('\n', '<br>')
    html_body = html_body.replace(
        f"To ACCEPT, click here: {accept_link}", 
        f'<br><a href="{accept_link}" style="display:inline-block; padding:10px 20px; background-color:#28a745; color:white; text-decoration:none; border-radius:5px;">✅ ACCEPT REFERRAL</a>'
    )
    html_body = html_body.replace(
        f"To REJECT, click here: {reject_link}", 
        f'<br><a href="{reject_link}" style="display:inline-block; padding:10px 20px; background-color:#dc3545; color:white; text-decoration:none; border-radius:5px;">❌ REJECT REFERRAL</a>'
    )

    target_email = referral.target_doctor_email or referral.target_department_email
    subject = f"URGENT: Patient Referral - {referral.referring_facility.name}" if referral.referral_type == 'EMERGENCY' else f"Patient Referral - {referral.referring_facility.name}"

    send_mail(
        subject=subject,
        message=final_body,
        from_email="noreply@health.gov.ng",
        recipient_list=[target_email],
        html_message=html_body,
        fail_silently=False,
    )
