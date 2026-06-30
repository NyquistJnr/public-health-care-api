# referrals/services.py
from django.core.mail import send_mail
from django.core.signing import TimestampSigner
from django.conf import settings
from .models import Referral
from appointments.models import Appointment, Vitals
from consultations.models import Consultation


def _format_history_section(referral: Referral) -> str:
    """Builds the 'Recent Medical History' block for external referral emails."""
    patient = referral.patient
    lines = []

    # Last 10 appointments
    appointments = Appointment.objects.filter(patient=patient).order_by('-appointment_date', '-appointment_time')[:10]
    if appointments:
        lines.append("--- RECENT APPOINTMENTS (last 10) ---")
        for a in appointments:
            lines.append(
                f"  [{a.appointment_date}] {a.appointment_id} | "
                f"Type: {a.get_visit_type_display()} | "
                f"Status: {a.status} | "
                f"Reason: {a.reason_for_visit}"
            )
        lines.append("")

    # Last 10 vitals (skip blank auto-created records)
    vitals = Vitals.objects.filter(patient=patient).order_by('-created_at')[:10]
    has_vitals = False
    vitals_lines = ["--- RECENT VITALS (last 10) ---"]
    for v in vitals:
        if not v._has_measurements():
            continue
        has_vitals = True
        vitals_lines.append(
            f"  [{v.created_at.strftime('%Y-%m-%d')}] "
            f"BP: {v.blood_pressure or 'N/A'} | "
            f"Temp: {v.temperature or 'N/A'}°C | "
            f"Pulse: {v.pulse_rate or 'N/A'} bpm | "
            f"Weight: {v.weight_kg or 'N/A'} kg | "
            f"Height: {v.height_cm or 'N/A'} cm | "
            f"SPO2: {v.spo2 or 'N/A'}%"
        )
    if has_vitals:
        lines.extend(vitals_lines)
        lines.append("")

    # Last 10 consultation notes
    consultations = Consultation.objects.filter(patient=patient).order_by('-created_at')[:10]
    if consultations:
        lines.append("--- RECENT CONSULTATION NOTES (last 10) ---")
        for c in consultations:
            lines.append(
                f"  [{c.created_at.strftime('%Y-%m-%d')}] {c.consultation_id}"
            )
            lines.append(f"    Chief Complaint: {c.chief_complaint}")
            lines.append(f"    Primary Diagnosis: {c.primary_diagnosis}")
            if c.secondary_diagnosis:
                lines.append(f"    Secondary Diagnosis: {c.secondary_diagnosis}")
            lines.append(f"    Treatment Plan: {c.treatment_plan}")
            if c.additional_notes:
                lines.append(f"    Notes: {c.additional_notes}")
        lines.append("")

    return "\n".join(lines)


def compile_and_send_external_referral(referral: Referral, request_host: str):
    patient = referral.patient
    appointment = referral.appointment

    signer = TimestampSigner()

    token_accept = signer.sign(f"{referral.id}:ACCEPTED")
    token_reject = signer.sign(f"{referral.id}:REJECTED")

    frontend_base_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')

    accept_link = f"{frontend_base_url}/referrals/action/?token={token_accept}"
    reject_link = f"{frontend_base_url}/referrals/action/?token={token_reject}"

    consultation = getattr(appointment, 'consultation', None)
    vitals = appointment.vitals.filter().order_by('created_at').last()

    # Current-appointment demographics + vitals + consultation
    medical_text = "--- PATIENT DEMOGRAPHICS ---\n"
    medical_text += f"Name: {patient.get_full_name()} (ID: {patient.patient_profile.patient_id})\n"
    medical_text += f"Age: {patient.patient_profile.age_group} | Sex: {patient.patient_profile.get_sex_display()}\n"
    if patient.patient_profile.blood_group:
        medical_text += f"Blood Group: {patient.patient_profile.blood_group} | Genotype: {patient.patient_profile.genotype}\n"
    if patient.patient_profile.allergies:
        medical_text += f"Allergies: {patient.patient_profile.allergies}\n"
    if patient.patient_profile.chronic_conditions:
        medical_text += f"Chronic Conditions: {patient.patient_profile.chronic_conditions}\n"
    medical_text += "\n"

    if vitals and vitals._has_measurements():
        medical_text += "--- CURRENT APPOINTMENT VITALS ---\n"
        medical_text += (
            f"BP: {vitals.blood_pressure or 'N/A'} | "
            f"Temp: {vitals.temperature or 'N/A'}°C | "
            f"Pulse: {vitals.pulse_rate or 'N/A'} bpm | "
            f"SPO2: {vitals.spo2 or 'N/A'}%\n\n"
        )

    if consultation:
        medical_text += "--- CURRENT CONSULTATION NOTES ---\n"
        medical_text += f"Chief Complaint: {consultation.chief_complaint}\n"
        medical_text += f"Primary Diagnosis: {consultation.primary_diagnosis}\n"
        medical_text += f"Treatment Plan: {consultation.treatment_plan}\n\n"

    # Historical records
    history_text = _format_history_section(referral)

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
        f"{'=' * 50}\n"
        f"RECENT MEDICAL HISTORY\n"
        f"{'=' * 50}\n"
        f"{history_text}"
        f"{'=' * 50}\n\n"
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
    subject = (
        f"URGENT: Patient Referral - {referral.referring_facility.name}"
        if referral.referral_type == 'EMERGENCY'
        else f"Patient Referral - {referral.referring_facility.name}"
    )

    send_mail(
        subject=subject,
        message=final_body,
        from_email="noreply@health.gov.ng",
        recipient_list=[target_email],
        html_message=html_body,
        fail_silently=False,
    )
